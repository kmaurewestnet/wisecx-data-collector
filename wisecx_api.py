"""WiseCX API client for interacting with the WiseCX API.

This module provides a client for interacting with the WiseCX API,
handling authentication, requests, and response parsing.
"""

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

# Deshabilitar advertencias de SSL inseguro (solo para desarrollo)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class WiseCXAPIError(Exception):
    """Custom exception for WiseCX API errors."""
    pass

class WiseCXAPITimeoutError(WiseCXAPIError):
    """Exception raised when an API request times out."""
    pass

class WiseCXAPIAuthenticationError(WiseCXAPIError):
    """Exception raised when authentication fails."""
    pass

class WiseCXAPI:
    """Client for interacting with the WiseCX API."""
    
    def __init__(self):
        """Initialize the WiseCX API client."""
        load_dotenv()
        self.api_key = os.getenv('WISECX_API_KEY')
        self.base_url = os.getenv('WISECX_API_BASE_URL', 'https://api.wcx.cloud/core/v1')
        self.jwt_token = None
        self.token_expiry = None
        
        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,  # Increased retries
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]  # Allow retries on POST requests
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default timeout
        self.timeout = (30, 30)  # (connect timeout, read timeout)
        
        # Authenticate and get JWT token
        self._authenticate()
    
    def _is_token_expired(self) -> bool:
        """Check if the current JWT token is expired."""
        if not self.token_expiry:
            return True
        return datetime.utcnow() >= self.token_expiry
    
    def _authenticate(self) -> None:
        """Authenticate with the API and get JWT token."""
        try:
            url = f"{self.base_url}/authenticate"
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key
            }
            params = {'user': 'westnet'}
            
            logger.info(f"Attempting authentication with API key: {self.api_key[:5]}...")
            
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout,
                verify=False
            )
            
            logger.info(f"Authentication response status: {response.status_code}")
            
            response.raise_for_status()
            
            try:
                data = response.json()
                logger.info(f"Authentication response data: {data}")
                
                self.jwt_token = data.get('token')
                
                if not self.jwt_token:
                    raise WiseCXAPIAuthenticationError("No JWT token found in authentication response")
                
                # Set token expiry to 55 minutes from now (assuming 1-hour token validity)
                self.token_expiry = datetime.utcnow() + timedelta(minutes=55)
                
                logger.info(f"Successfully obtained JWT token: {self.jwt_token[:10]}...")
                
                self.session.headers.update({
                    'Authorization': f'Bearer {self.jwt_token}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'x-api-key': self.api_key
                })
                
            except json.JSONDecodeError as e:
                raise WiseCXAPIAuthenticationError(f"Invalid JSON response during authentication: {str(e)}")
                
        except requests.exceptions.Timeout:
            raise WiseCXAPITimeoutError("Authentication request timed out")
        except requests.exceptions.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"Authentication Error details: {error_data}")
                except:
                    logger.error(f"Response content: {e.response.text}")
            raise WiseCXAPIAuthenticationError(f"Authentication failed: {str(e)}")
    
    def _make_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a request to the WiseCX API."""
        url = f"{self.base_url}/{endpoint}"
        
        # Check if token needs refresh
        if self._is_token_expired():
            logger.warning("Token expired, reauthenticating...")
            self._authenticate()
        
        try:
            response = self.session.request(
                method, 
                url, 
                params=params, 
                verify=False,
                timeout=self.timeout
            )
            
            # Handle specific status codes
            if response.status_code == 401:
                logger.warning("Token expired, attempting to reauthenticate...")
                self._authenticate()
                response = self.session.request(
                    method, 
                    url, 
                    params=params, 
                    verify=False,
                    timeout=self.timeout
                )
            
            response.raise_for_status()
            
            # Validate response content
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
                    error_data = e.response.json()
                    logger.error(f"API Error details: {error_data}")
                except:
                    logger.error(f"Response content: {e.response.text}")
            raise WiseCXAPIError(f"API request failed: {str(e)}")
    
    def get_all_surveys(self) -> List[Dict]:
        """Get all surveys."""
        response = self._make_request('GET', 'surveys')
        if not isinstance(response, list):
            logger.warning(f"Unexpected response format for surveys: {response}")
            return []
        return response
    
    def get_survey_responses(self, survey_id: str, limit: int = 100, page: int = 1) -> List[Dict]:
        """Get responses for a specific survey with pagination support.
        
        Args:
            survey_id: ID of the survey to get responses for
            limit: Maximum number of responses per page
            page: Page number to retrieve (1-based)
            
        Returns:
            List of response dictionaries
        """
        params = {
            'limit': limit,
            'page': page
        }
        logger.info(f"Getting survey responses for survey {survey_id}, page {page}, limit {limit}")
        response = self._make_request('GET', f'surveys/{survey_id}/responses', params)
        
        if isinstance(response, dict) and 'data' in response:
            logger.info(f"Found {len(response['data'])} responses in data field for page {page}")
            return response['data']
        elif isinstance(response, list):
            logger.info(f"Found {len(response)} responses in direct list for page {page}")
            return response
        else:
            logger.warning(f"Unexpected response format for page {page}: {response}")
            return []
    
    def get_case(self, case_id: str) -> Optional[Dict]:
        """Get details for a specific case."""
        params = {
            'fields': 'id,number,group_id,user_id,contact_id,status,tags,created_at'
        }
        try:
            return self._make_request('GET', f'cases/{case_id}', params)
        except WiseCXAPIError as e:
            logger.error(f"Failed to get case {case_id}: {str(e)}")
            return None
    
    def get_contact(self, contact_id: str) -> Optional[Dict]:
        """Get details for a specific contact."""
        params = {
            'fields': 'id,email,personal_id,phone,name'
        }
        try:
            return self._make_request('GET', f'contacts/{contact_id}', params)
        except WiseCXAPIError as e:
            logger.error(f"Failed to get contact {contact_id}: {str(e)}")
            return None

    def _handle_rate_limit(self, response: requests.Response) -> None:
        """Handle rate limiting headers from API response.
        
        Args:
            response: The API response containing rate limit headers
        """
        self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 100))
        self.rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
        
        if self.rate_limit_remaining <= 5:
            wait_time = max(0, self.rate_limit_reset - time.time())
            if wait_time > 0:
                logger.warning(f"Rate limit nearly exceeded. Waiting {wait_time:.2f} seconds")
                time.sleep(wait_time)

    def get_surveys(self, page: int = 1, per_page: int = 100) -> List[Dict]:
        """Get surveys with pagination support.
        
        Args:
            page: Page number to retrieve (not used in current API version)
            per_page: Number of items per page (not used in current API version)
            
        Returns:
            List of dicts containing survey data with id, guid, and name
        """
        # La API actual no soporta paginación, así que ignoramos los parámetros
        response = self._make_request('GET', 'surveys')
        
        # Log the structure of the first survey if available
        if isinstance(response, list) and response:
            logger.info(f"Survey structure: {response[0]}")
        elif isinstance(response, dict) and response.get('data'):
            logger.info(f"Survey structure: {response['data'][0]}")
            
        # La respuesta es una lista directa de encuestas
        if isinstance(response, list):
            return response
            
        # Si la respuesta tiene un formato diferente, intentamos extraer la lista
        return response.get('data', [])

    def get_customer(self, customer_id: str) -> Dict:
        """Get customer details by ID.
        
        Args:
            customer_id: ID of the customer/contact
            
        Returns:
            Dict containing customer data with id, email, personal_id, phone, name, etc.
        """
        params = {
            'fields': 'id,email,personal_id,phone,name,guid'
        }
        return self._make_request('GET', f'contacts/{customer_id}', params)

    def get_customer_contacts(self, customer_id: str) -> List[Dict]:
        """Get contacts associated with a customer.
        
        Args:
            customer_id: ID of the customer
            
        Returns:
            List of dicts containing contact data
        """
        # En la nueva API, los contactos se obtienen directamente con get_customer
        customer = self.get_customer(customer_id)
        return [customer] if customer else [] 