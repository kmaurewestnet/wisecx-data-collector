"""WiseCX API client."""

import requests
from typing import Dict, List, Optional
from loguru import logger
import os
from dotenv import load_dotenv
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
import json
from datetime import datetime, timedelta

load_dotenv()

# Disable SSL warnings only when explicitly configured (e.g. dev environments without valid cert)
_SSL_VERIFY = os.getenv('WISECX_SSL_VERIFY', 'true').lower() not in ('false', '0', 'no')
if not _SSL_VERIFY:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class WiseCXAPIError(Exception):
    """Base exception for WiseCX API errors."""
    pass


class WiseCXAPITimeoutError(WiseCXAPIError):
    """Raised when an API request times out."""
    pass


class WiseCXAPIAuthenticationError(WiseCXAPIError):
    """Raised when authentication fails."""
    pass


class WiseCXAPI:
    """Client for interacting with the WiseCX API."""

    def __init__(self):
        self.api_key = os.getenv('WISECX_API_KEY')
        self.base_url = os.getenv('WISECX_API_BASE_URL', 'https://api.wcx.cloud/core/v1')
        self.wisecx_user = os.getenv('WISECX_USER', 'westnet')
        self.jwt_token = None
        self.token_expiry = None

        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.timeout = (30, 30)

        self._authenticate()

    def _is_token_expired(self) -> bool:
        if not self.token_expiry:
            return True
        return datetime.utcnow() >= self.token_expiry

    def _authenticate(self) -> None:
        """Authenticate with the API and obtain a JWT token."""
        try:
            url = f"{self.base_url}/authenticate"
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key
            }
            params = {'user': self.wisecx_user}

            logger.info("Attempting authentication...")

            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout,
                verify=_SSL_VERIFY
            )

            response.raise_for_status()

            try:
                data = response.json()
                self.jwt_token = data.get('token')

                if not self.jwt_token:
                    raise WiseCXAPIAuthenticationError("No JWT token in authentication response")

                # Assume 1-hour token validity; refresh 5 minutes early
                self.token_expiry = datetime.utcnow() + timedelta(minutes=55)
                logger.info("Authentication successful")

                self.session.headers.update({
                    'Authorization': f'Bearer {self.jwt_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'x-api-key': self.api_key
                })

            except json.JSONDecodeError as e:
                raise WiseCXAPIAuthenticationError(f"Invalid JSON in authentication response: {str(e)}")

        except requests.exceptions.Timeout:
            raise WiseCXAPITimeoutError("Authentication request timed out")
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                try:
                    logger.error(f"Authentication error details: {e.response.json()}")
                except Exception:
                    logger.error(f"Authentication response: {e.response.text}")
            raise WiseCXAPIAuthenticationError(f"Authentication failed: {str(e)}")

    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a request to the WiseCX API."""
        url = f"{self.base_url}/{endpoint}"

        if self._is_token_expired():
            logger.warning("Token expired, reauthenticating...")
            self._authenticate()

        try:
            response = self.session.request(
                method,
                url,
                params=params,
                verify=_SSL_VERIFY,
                timeout=self.timeout
            )

            if response.status_code == 401:
                logger.warning("Received 401, reauthenticating...")
                self._authenticate()
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    verify=_SSL_VERIFY,
                    timeout=self.timeout
                )

            response.raise_for_status()

            if not response.text:
                raise WiseCXAPIError("Empty response received")

            try:
                return response.json()
            except json.JSONDecodeError as e:
                raise WiseCXAPIError(f"Invalid JSON response: {str(e)}")

        except requests.exceptions.Timeout:
            raise WiseCXAPITimeoutError(f"Request to {endpoint} timed out")
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                try:
                    logger.error(f"API error details: {e.response.json()}")
                except Exception:
                    logger.error(f"API response content: {e.response.text}")
            raise WiseCXAPIError(f"API request failed: {str(e)}")

    def get_all_surveys(self) -> List[Dict]:
        """Return all surveys."""
        response = self._make_request('GET', 'surveys')
        if not isinstance(response, list):
            logger.warning(f"Unexpected surveys response format: {type(response)}")
            return []
        return response

    def get_survey_responses(self, survey_id: str, limit: int = 100, page: int = 1) -> List[Dict]:
        """Return paginated responses for a survey.

        The API returns HTTP 400 with 'Survey Responses Not Found' when the survey
        has no responses — this is treated as an empty list, not an error.
        """
        # Only fetch responded surveys; 'not_responded' entries have empty answers
        params = {'limit': limit, 'page': page, 'status': 'responded'}
        logger.info(f"Getting responses for survey {survey_id}, page {page}, limit {limit}")

        try:
            response = self._make_request('GET', f'surveys/{survey_id}/responses', params)
        except WiseCXAPIError as e:
            error_str = str(e)
            if 'Survey Responses Not Found' in error_str or '400' in error_str:
                logger.info(f"Survey {survey_id} has no responses")
                return []
            raise

        if isinstance(response, dict) and 'data' in response:
            data = response['data']
            if not isinstance(data, list):
                logger.warning(f"Unexpected 'data' field type for survey {survey_id}: {type(data)}")
                return []
            logger.info(f"Found {len(data)} responses for survey {survey_id} (page {page})")
            return data
        elif isinstance(response, list):
            logger.info(f"Found {len(response)} responses for survey {survey_id} (page {page})")
            return response
        else:
            logger.warning(f"Unexpected response format for survey {survey_id}: {response}")
            return []

    def get_case(self, case_id: str) -> Optional[Dict]:
        """Return details for a specific case."""
        params = {'fields': 'id,number,group_id,user_id,contact_id,status,tags,created_at'}
        try:
            return self._make_request('GET', f'cases/{case_id}', params)
        except WiseCXAPIError as e:
            logger.error(f"Failed to get case {case_id}: {str(e)}")
            return None

    def get_contact(self, contact_id: str) -> Optional[Dict]:
        """Return details for a specific contact."""
        params = {'fields': 'id,email,personal_id,phone,name'}
        try:
            return self._make_request('GET', f'contacts/{contact_id}', params)
        except WiseCXAPIError as e:
            logger.error(f"Failed to get contact {contact_id}: {str(e)}")
            return None
