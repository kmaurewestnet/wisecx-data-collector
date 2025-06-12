"""Database management for the WiseCX data collector.

This module provides database operations for storing and retrieving
contact, survey, case, and survey response data from the WiseCX API.
"""

from sqlalchemy import create_engine, Index, event, text
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Base, Contact, Survey, Case, SurveyResponse
from loguru import logger
import os
from dotenv import load_dotenv
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
from typing import Optional, Dict, List, Any
from sqlalchemy.exc import SQLAlchemyError


load_dotenv()

class DatabaseManager:
    """Manages database operations for the WiseCX data collector.
    
    This class handles database connections, initialization, and CRUD
    operations for contact, survey, and case data.
    
    Attributes:
        db_type (str): Type of database (postgresql or sqlite)
        connection_string (str): Database connection string
        engine: SQLAlchemy engine instance
        Session: SQLAlchemy session factory
    """
    
    def __init__(self) -> None:
        """Initialize the database manager with configuration from environment."""
        self.db_type = os.getenv('DB_TYPE', 'sqlite')
        
        if self.db_type == 'postgresql':
            self.connection_string = (
                f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
                f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
            )
        else:
            self.connection_string = 'sqlite:///wisecx_data.db'
            
        self.engine = create_engine(self.connection_string)
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        # Configure SQLite for better performance
        if self.db_type == 'sqlite':
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=10000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=30000000000")
                cursor.close()
        
    def init_db(self) -> None:
        """Initialize the database by creating all tables."""
        # Create tables
        Base.metadata.create_all(self.engine)
        logger.info("Database initialized successfully")
        
    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
        
    def _validate_contact_data(self, data: Dict[str, Any]) -> bool:
        """Validate contact data before saving."""
        required_fields = ['id']
        return all(field in data for field in required_fields)
    
    def _validate_survey_data(self, data: Dict[str, Any]) -> bool:
        """Validate survey data before saving."""
        required_fields = ['id', 'guid']
        return all(field in data for field in required_fields)
    
    def _validate_case_data(self, data: Dict[str, Any]) -> bool:
        """Validate case data before saving."""
        required_fields = ['id']
        return all(field in data for field in required_fields)
    
    def _validate_survey_response_data(self, data: Dict[str, Any]) -> bool:
        """Validate survey response data before saving."""
        required_fields = ['id']
        return all(field in data for field in required_fields)
    
    def save_contact(self, contact_data: dict) -> Optional[Contact]:
        """Save or update a contact record.
        
        Args:
            contact_data: Dictionary containing contact data from API
            
        Returns:
            Contact: The saved or updated contact record
            
        Raises:
            Exception: If there's an error saving the contact
        """
        if not self._validate_contact_data(contact_data):
            logger.error(f"Invalid contact data: {contact_data}")
            return None
        
        # Convert wise_id early for error handling
        wise_id = str(contact_data['id'])
        

            
        try:
            with self.session_scope() as session:

                
                contact = session.query(Contact).filter_by(wise_id=wise_id).first()
                

                
                # Convert last_update to datetime if it exists
                last_update = None
                if contact_data.get('last_update'):
                    try:
                        last_update = datetime.strptime(contact_data['last_update'], '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        logger.warning(f"Invalid last_update format for contact {wise_id}")
                
                contact_params = {
                    'wise_id': wise_id,
                    'name': contact_data.get('name'),
                    'email': contact_data.get('email'),
                    'phone': contact_data.get('phone'),
                    'personal_id': contact_data.get('personal_id'),
                    'last_update': last_update
                }
                
                if not contact:

                    
                    contact = Contact(**contact_params)
                    session.add(contact)
                    logger.info(f"Created new contact with wise_id: {wise_id}")
                else:

                    
                    contact.name = contact_data.get('name')
                    contact.email = contact_data.get('email')
                    contact.phone = contact_data.get('phone')
                    contact.personal_id = contact_data.get('personal_id')
                    contact.last_update = last_update
                    logger.info(f"Updated existing contact with wise_id: {wise_id}")
                
                # Ensure the contact is attached to the session
                session.flush()
                

                
                return contact
                
        except Exception as e:
            logger.error(f"Error saving contact: {str(e)}")

            return None
            
    def save_survey(self, survey_data: dict) -> Optional[Survey]:
        """Save or update a survey record.
        
        Args:
            survey_data: Dictionary containing survey data from API
            
        Returns:
            Survey: The saved or updated survey record
            
        Raises:
            Exception: If there's an error saving the survey
        """
        if not self._validate_survey_data(survey_data):
            logger.error(f"Invalid survey data: {survey_data}")
            return None
            
        try:
            with self.session_scope() as session:
                wise_id = str(survey_data['id'])
                survey = session.query(Survey).filter_by(wise_id=wise_id).first()
                
                if not survey:
                    survey = Survey(
                        wise_id=wise_id,
                        guid=survey_data.get('guid'),
                        name=survey_data.get('name')
                    )
                    session.add(survey)
                else:
                    survey.guid = survey_data.get('guid')
                    survey.name = survey_data.get('name')
                
                session.flush()
                return survey
                
        except Exception as e:
            logger.error(f"Error saving survey: {str(e)}")
            return None
            
    def save_case(self, case_data: dict) -> Optional[Case]:
        """Save or update a case record.
        
        Args:
            case_data: Dictionary containing case data from API
            
        Returns:
            Case: The saved or updated case record
            
        Raises:
            Exception: If there's an error saving the case
        """
        if not self._validate_case_data(case_data):
            logger.error(f"Invalid case data: {case_data}")
            return None
        
        # Convert case_id early for error handling
        case_id = str(case_data['id'])
        

            
        try:
            with self.session_scope() as session:

                
                case = session.query(Case).filter_by(case_id=case_id).first()
                

                
                # Convertir campos de fecha si existen
                created_at = None
                if case_data.get('created_at'):
                    try:
                        # Try different common datetime formats
                        created_at_str = case_data['created_at']
                        
                        # Common formats to try
                        formats = [
                            '%Y-%m-%dT%H:%M:%S',           # 2023-12-01T15:30:45
                            '%Y-%m-%d %H:%M:%S',           # 2023-12-01 15:30:45
                            '%Y-%m-%dT%H:%M:%S.%f',        # 2023-12-01T15:30:45.123456
                            '%Y-%m-%dT%H:%M:%SZ',          # 2023-12-01T15:30:45Z
                            '%Y-%m-%dT%H:%M:%S.%fZ',       # 2023-12-01T15:30:45.123456Z
                            '%Y-%m-%d',                    # 2023-12-01
                        ]
                        
                        for fmt in formats:
                            try:
                                created_at = datetime.strptime(created_at_str, fmt)
                                break
                            except ValueError:
                                continue
                        
                        if created_at is None:
                            logger.warning(f"Could not parse created_at '{created_at_str}' for case {case_id} with any known format")
                            
                    except Exception as e:
                        logger.warning(f"Error parsing created_at for case {case_id}: {str(e)}")
                
                case_params = {
                    'case_id': case_id,
                    'group_id': case_data.get('group_id'),
                    'number': str(case_data.get('number')),
                    'contact_id': case_data.get('contact_id'),
                    'status': case_data.get('status'),
                    'tags': case_data.get('tags', []),
                    'created_at': created_at
                }
                
                if not case:

                    
                    case = Case(**case_params)
                    session.add(case)
                    logger.info(f"Created new case with case_id: {case_id}")
                else:

                    
                    # No actualizamos case_id ni id ya que son la clave primaria
                    # También preservamos created_at - no lo actualizamos en ejecuciones futuras
                    case.group_id = case_data.get('group_id')
                    case.number = str(case_data.get('number'))
                    case.contact_id = case_data.get('contact_id')
                    case.status = case_data.get('status')
                    case.tags = case_data.get('tags', [])
                    # created_at se mantiene con su valor original - NO se actualiza
                    logger.info(f"Updated existing case with case_id: {case_id} (preserved original created_at: {case.created_at})")
                
                session.flush()
                

                
                return case
                
        except Exception as e:
            logger.error(f"Error saving case: {str(e)}")

            return None
            
    def save_survey_response(self, response_data: dict, survey_id: str) -> Optional[SurveyResponse]:
        """Save or update a survey response record.
        
        Args:
            response_data: Dictionary containing survey response data from API
            survey_id: ID of the associated survey
            
        Returns:
            SurveyResponse: The saved or updated survey response record, or None if responses array is empty
            
        Raises:
            Exception: If there's an error saving the survey response
        """
        if not self._validate_survey_response_data(response_data):
            logger.error(f"Invalid survey response data: {response_data}")
            return None
            
        try:
            with self.session_scope() as session:
                wise_id = str(response_data['id'])
                response = session.query(SurveyResponse).filter_by(wise_id=wise_id).first()
                
                # Convert responded_at to datetime if it exists
                responded_at = None
                if response_data.get('responded_at'):
                    try:
                        responded_at = datetime.strptime(response_data['responded_at'], '%Y-%m-%dT%H:%M:%S')
                    except ValueError:
                        logger.warning(f"Invalid responded_at format for response {wise_id}")
                
                # Convertir las respuestas a un formato consistente
                responses = response_data.get('response', {})
                if isinstance(responses, list):
                    # Si es una lista, convertir a diccionario usando el guid como clave
                    responses_dict = {}
                    for resp in responses:
                        if isinstance(resp, dict) and 'guid' in resp:
                            responses_dict[resp['guid']] = resp.get('response', '')
                    responses = responses_dict
                
                if not responses or (isinstance(responses, (list, dict)) and len(responses) == 0):
                    logger.warning(f"Skipping survey response {wise_id} - empty responses")
                    return None
                
                if not response:
                    response = SurveyResponse(
                        wise_id=wise_id,
                        survey_id=survey_id,
                        case_id=response_data.get('case_id'),
                        contact_id=response_data.get('contact_id'),
                        responses=responses,
                        responded_at=responded_at
                    )
                    session.add(response)
                else:
                    response.survey_id = survey_id
                    response.case_id = response_data.get('case_id')
                    response.contact_id = response_data.get('contact_id')
                    response.responses = responses
                    response.responded_at = responded_at
                
                session.flush()
                return response
                
        except Exception as e:
            logger.error(f"Error saving survey response: {str(e)}")
            return None
    
    def cleanup_old_data(self, days: int = 90) -> None:
        """Clean up data older than specified days."""
        try:
            with self.session_scope() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                # Delete old survey responses
                old_responses = session.query(SurveyResponse).filter(
                    SurveyResponse.created_at < cutoff_date
                ).all()
                for response in old_responses:
                    session.delete(response)
                
                # Delete old cases
                old_cases = session.query(Case).filter(
                    Case.created_at < cutoff_date
                ).all()
                for case in old_cases:
                    session.delete(case)
                
                logger.info(f"Cleaned up data older than {days} days")
                
        except Exception as e:
            logger.error(f"Error cleaning up old data: {str(e)}")
            raise 