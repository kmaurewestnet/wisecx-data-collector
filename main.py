"""Main entry point for the WiseCX data collector application.

This module orchestrates the data collection process from the WiseCX API
and stores the data in the configured database.
"""

from wisecx_api import WiseCXAPI, WiseCXAPIError, WiseCXAPITimeoutError
from database import DatabaseManager
from loguru import logger
import sys
import os
from dotenv import load_dotenv
from typing import List, Dict, Optional
import time
from datetime import datetime, timedelta
import json


# Configure logging
logger.remove()
logger.add(sys.stdout, level=os.getenv('LOG_LEVEL', 'INFO'))
logger.add(
    "wisecx_collector.log",
    rotation="1 day",
    retention="30 days",
    compression="zip"
)

class DataCollector:
    """Main data collection orchestrator."""
    
    def __init__(self):
        """Initialize the data collector."""
        self.api = WiseCXAPI()
        self.db = DatabaseManager()
        self.db.init_db()
        self.batch_size = int(os.getenv('BATCH_SIZE', '100'))
        self.max_retries = int(os.getenv('MAX_RETRIES', '3'))
        self.retry_delay = int(os.getenv('RETRY_DELAY', '5'))
        
    def _has_valid_responses(self, response_data: Dict) -> bool:
        """Check if survey response has valid (non-empty) responses.
        
        Args:
            response_data: Dictionary containing survey response data
            
        Returns:
            bool: True if response has valid responses, False otherwise
        """
        responses = response_data.get('response', [])
        
        # Check if responses is empty
        if not responses:
            return False
            
        # If it's a list, check if it has actual response data
        if isinstance(responses, list):
            # Check if any response has actual content
            for resp in responses:
                if isinstance(resp, dict) and resp.get('response'):
                    return True
            return False
            
        # If it's a dict, check if it has content
        if isinstance(responses, dict):
            return len(responses) > 0
            
        return True
        
    def process_survey_batch(self, surveys: List[Dict]) -> None:
        """Process a batch of surveys.
        
        Args:
            surveys: List of survey dictionaries to process
        """
        for survey in surveys:
            try:
                survey_id = survey['id']
                logger.info(f"Processing survey {survey_id}")
                
                # Save survey first
                saved_survey = self.db.save_survey(survey)
                if not saved_survey:
                    logger.error(f"Failed to save survey {survey_id}")
                    continue
                
                # Get responses for this survey (only first page)
                all_responses = []
                page = 1
                
                # Only get first page to limit data collection
                try:
                    responses = self.api.get_survey_responses(survey_id, limit=self.batch_size, page=page)
                    if responses:
                        logger.info(f"Found {len(responses)} responses for survey {survey_id}, page {page} (limited to first page)")
                        all_responses.extend(responses)
                    else:
                        logger.info(f"No responses found for survey {survey_id}, page {page}")
                        
                except WiseCXAPIError as e:
                    logger.error(f"API error getting responses for survey {survey_id}, page {page}: {str(e)}")
                    
                except Exception as e:
                    logger.error(f"Unexpected error getting responses for survey {survey_id}, page {page}: {str(e)}")
                
                logger.info(f"Total responses found for survey {survey_id}: {len(all_responses)}")
                
                if not all_responses:
                    logger.warning(f"No responses found for survey {survey_id} across all pages")
                    continue
                
                # Process responses in batches
                for i in range(0, len(all_responses), self.batch_size):
                    batch = all_responses[i:i + self.batch_size]
                    self.process_response_batch(batch, survey_id)
                    
            except WiseCXAPIError as e:
                logger.error(f"API error processing survey {survey_id}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Error processing survey {survey_id}: {str(e)}")
                continue
    
    def process_response_batch(self, responses: List[Dict], survey_id: str) -> None:
        """Process a batch of survey responses.
        
        Args:
            responses: List of response dictionaries to process
            survey_id: ID of the survey these responses belong to
        """
        for response in responses:
            try:
                # First check if response has valid data
                if not self._has_valid_responses(response):
                    logger.warning(f"Skipping response {response.get('id')} - empty or invalid responses")
                    continue
                
                # Get and save contact FIRST (because case has foreign key to contact)
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
                            time.sleep(self.retry_delay)
                        except WiseCXAPITimeoutError:
                            if attempt == self.max_retries - 1:
                                logger.error(f"Failed to get contact {contact_id} after {self.max_retries} attempts")
                                continue
                            time.sleep(self.retry_delay * (attempt + 1))
                
                # Get and save case AFTER contact is saved
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
                            time.sleep(self.retry_delay)
                        except WiseCXAPITimeoutError:
                            if attempt == self.max_retries - 1:
                                logger.error(f"Failed to get case {case_id} after {self.max_retries} attempts")
                                continue
                            time.sleep(self.retry_delay * (attempt + 1))
                
                # Only save survey response if we have both case and contact
                if saved_case and saved_contact:
                    saved_response = self.db.save_survey_response(response, str(survey_id))
                    if not saved_response:
                        logger.error(f"Failed to save response for survey {survey_id}")
                        continue
                    
                    logger.info(f"Successfully processed response {response['id']} for survey {survey_id}")
                else:
                    logger.warning(f"Skipping response {response['id']} - missing case or contact")
                
            except Exception as e:
                logger.error(f"Error processing response for survey {survey_id}: {str(e)}")
                continue
    
    def run(self) -> None:
        """Run the data collection process."""
        try:
            # Get all surveys
            surveys = self.api.get_all_surveys()
            logger.info(f"Found {len(surveys)} surveys")
            
            # Process surveys in batches
            for i in range(0, len(surveys), self.batch_size):
                batch = surveys[i:i + self.batch_size]
                self.process_survey_batch(batch)
                
            # Clean up old data
            self.db.cleanup_old_data(days=90)
            
        except WiseCXAPIError as e:
            logger.error(f"API error in main process: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error in main process: {str(e)}")
            raise

def main():
    """Main function to collect and store WiseCX data."""
    try:
        collector = DataCollector()
        collector.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 