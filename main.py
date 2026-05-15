"""Main entry point for the WiseCX data collector application."""

from wisecx_api import WiseCXAPI, WiseCXAPIError, WiseCXAPITimeoutError
from database import DatabaseManager
from loguru import logger
import sys
import os
from dotenv import load_dotenv
from typing import List, Dict, Optional
import time
from datetime import datetime, timedelta


load_dotenv()

# Configure logging
logger.remove()
logger.add(sys.stdout, level=os.getenv('LOG_LEVEL', 'INFO'))
logger.add(
    "wisecx_collector.log",
    rotation="1 day",
    retention="30 days",
    compression="zip"
)

# Field names the API may use for the response ID and response content.
# The API structure is logged on first encounter so the correct names can be confirmed.
_RESPONSE_ID_FIELDS = ('id', 'response_id', 'survey_response_id')
_RESPONSE_CONTENT_FIELDS = ('responses', 'response', 'answers', 'data')


def _get_response_id(response_data: Dict) -> Optional[str]:
    """Return the response ID trying multiple possible field names."""
    for field in _RESPONSE_ID_FIELDS:
        value = response_data.get(field)
        if value is not None:
            return str(value)
    return None


def _get_response_content(response_data: Dict):
    """Return the response content trying multiple possible field names."""
    for field in _RESPONSE_CONTENT_FIELDS:
        value = response_data.get(field)
        if value is not None:
            return value, field
    return None, None


class DataCollector:
    """Main data collection orchestrator."""

    def __init__(self):
        self.api = WiseCXAPI()
        self.db = DatabaseManager()
        self.db.init_db()
        self.batch_size = int(os.getenv('BATCH_SIZE', '100'))
        self.max_retries = int(os.getenv('MAX_RETRIES', '3'))
        self.retry_delay = int(os.getenv('RETRY_DELAY', '5'))
        self._api_structure_logged = False

    def _log_response_structure(self, response_data: Dict) -> None:
        """Log the structure of the first API response for diagnostics."""
        if self._api_structure_logged:
            return
        self._api_structure_logged = True
        keys = list(response_data.keys()) if isinstance(response_data, dict) else type(response_data).__name__
        logger.info(f"[DIAG] First survey response keys: {keys}")
        # Log a sample of the first response (truncated for safety)
        sample = {k: str(v)[:80] for k, v in response_data.items()} if isinstance(response_data, dict) else str(response_data)[:200]
        logger.info(f"[DIAG] First survey response sample: {sample}")

    def _has_valid_responses(self, response_data: Dict) -> bool:
        """Return True if this response record is worth saving.

        A 'responded' record is always saved — it represents a meaningful event
        (survey delivered and acknowledged) even when answers are empty.
        A 'not_responded' record is only saved if it has actual answer content.
        """
        if response_data.get('status') == 'responded':
            return True

        content, _ = _get_response_content(response_data)
        if not content:
            return False
        if isinstance(content, list):
            return any(isinstance(item, dict) and item.get('response') for item in content)
        if isinstance(content, dict):
            return len(content) > 0
        return bool(content)

    def process_survey_batch(self, surveys: List[Dict]) -> None:
        """Process a batch of surveys, fetching all pages of responses."""
        for survey in surveys:
            try:
                survey_id = survey['id']
                logger.info(f"Processing survey {survey_id}")

                saved_survey = self.db.save_survey(survey)
                if not saved_survey:
                    logger.error(f"Failed to save survey {survey_id}")
                    continue

                page = 1
                total_responses = 0
                while True:
                    try:
                        responses = self.api.get_survey_responses(
                            survey_id, limit=self.batch_size, page=page
                        )
                    except WiseCXAPIError as e:
                        logger.error(f"API error getting responses for survey {survey_id} page {page}: {str(e)}")
                        break
                    except Exception as e:
                        logger.error(f"Unexpected error getting responses for survey {survey_id} page {page}: {str(e)}")
                        break

                    if not responses:
                        if page == 1:
                            logger.info(f"No responses found for survey {survey_id}")
                        break

                    total_responses += len(responses)
                    logger.info(f"Survey {survey_id} page {page}: {len(responses)} responses")
                    self.process_response_batch(responses, str(survey_id))

                    if len(responses) < self.batch_size:
                        break  # last page
                    page += 1

                if total_responses > 0:
                    logger.info(f"Survey {survey_id}: {total_responses} total responses processed ({page} pages)")

            except WiseCXAPIError as e:
                logger.error(f"API error processing survey {survey['id']}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Error processing survey {survey['id']}: {str(e)}")
                continue

    def process_response_batch(self, responses: List[Dict], survey_id: str) -> None:
        """Process a batch of survey responses."""
        for response in responses:
            try:
                # Log structure on first occurrence to help diagnose field name issues
                self._log_response_structure(response)

                response_id = _get_response_id(response)

                # Skip surveys sent but not yet answered
                if response.get('status') == 'not_responded':
                    logger.debug(f"Skipping response {response_id} - not yet responded")
                    continue

                if not self._has_valid_responses(response):
                    logger.warning(f"Skipping response {response_id} - empty or invalid responses")
                    continue

                # Save contact first (case has FK to contact)
                contact_id = response.get('contact_id')
                saved_contact = None
                if contact_id:
                    for attempt in range(self.max_retries):
                        try:
                            contact_data = self.api.get_contact(str(contact_id))
                            if contact_data:
                                saved_contact = self.db.save_contact(contact_data)
                                if saved_contact:
                                    break
                            # Only sleep when about to retry, not on success
                            if attempt < self.max_retries - 1:
                                time.sleep(self.retry_delay)
                        except WiseCXAPITimeoutError:
                            if attempt == self.max_retries - 1:
                                logger.error(
                                    f"Failed to get contact {contact_id} after {self.max_retries} attempts"
                                )
                            else:
                                time.sleep(self.retry_delay * (attempt + 1))

                # Save case after contact
                case_id = response.get('case_id')
                saved_case = None
                if case_id:
                    for attempt in range(self.max_retries):
                        try:
                            case_data = self.api.get_case(str(case_id))
                            if case_data:
                                saved_case = self.db.save_case(case_data)
                                if saved_case:
                                    break
                            if attempt < self.max_retries - 1:
                                time.sleep(self.retry_delay)
                        except WiseCXAPITimeoutError:
                            if attempt == self.max_retries - 1:
                                logger.error(
                                    f"Failed to get case {case_id} after {self.max_retries} attempts"
                                )
                            else:
                                time.sleep(self.retry_delay * (attempt + 1))

                if saved_case and saved_contact:
                    saved_response = self.db.save_survey_response(response, str(survey_id))
                    if saved_response:
                        logger.info(f"Successfully processed response {response_id} for survey {survey_id}")
                    else:
                        logger.error(f"Failed to save response {response_id} for survey {survey_id}")
                else:
                    logger.warning(f"Skipping response {response_id} - missing case or contact")

            except Exception as e:
                logger.error(f"Error processing response for survey {survey_id}: {str(e)}")
                continue

    def run(self) -> None:
        """Run the data collection process."""
        try:
            surveys = self.api.get_all_surveys()
            logger.info(f"Found {len(surveys)} surveys")

            for i in range(0, len(surveys), self.batch_size):
                batch = surveys[i:i + self.batch_size]
                self.process_survey_batch(batch)

            self.db.cleanup_old_data(days=90)

        except WiseCXAPIError as e:
            logger.error(f"API error in main process: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error in main process: {str(e)}")
            raise


def main():
    """Entry point."""
    try:
        collector = DataCollector()
        collector.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
