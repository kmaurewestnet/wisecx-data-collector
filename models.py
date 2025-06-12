"""Database models for the WiseCX data collector application.

This module defines the SQLAlchemy models for storing customer, contact,
survey, case, and survey response data from the WiseCX API.
"""

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Customer(Base):
    """SQLAlchemy model for storing customer information.
    
    This model represents a customer in the WiseCX system and maintains
    relationships with their contacts and surveys.
    
    Attributes:
        id (int): Primary key
        wise_id (str): WiseCX customer ID
        name (str): Customer name
        customer_number (str): Customer number
        phone (str): Customer phone number
        created_at (datetime): Record creation timestamp
        updated_at (datetime): Record last update timestamp
        contacts (List[Contact]): Related contact records
        cases (List[Case]): Related case records
    """
    
    __tablename__ = 'customers'
    
    id = Column(Integer, primary_key=True)
    wise_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(255))
    customer_number = Column(String(50))
    phone = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    contacts = relationship("Contact", back_populates="customer")
    cases = relationship("Case", back_populates="customer")

class Contact(Base):
    """SQLAlchemy model for storing contact information.
    
    This model represents a contact associated with a customer in the
    WiseCX system.
    
    Attributes:
        id (int): Primary key
        wise_id (str): WiseCX contact ID
        customer_id (str): Customer ID (personal_id from API)
        name (str): Contact name
        email (str): Contact email
        phone (str): Contact phone number
        personal_id (str): Personal ID from API
        last_update (datetime): Last update timestamp
        created_at (datetime): Record creation timestamp
        updated_at (datetime): Record last update timestamp
        customer (Customer): Related customer record
        cases (List[Case]): Related case records
        survey_responses (List[SurveyResponse]): Related survey response records
    """
    
    __tablename__ = 'contacts'
    
    id = Column(Integer, primary_key=True)
    wise_id = Column(String(50), unique=True, nullable=False)
    customer_id = Column(String(50), ForeignKey('customers.wise_id'))
    name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    personal_id = Column(String(50))
    last_update = Column(DateTime)

    
    # Relationships
    customer = relationship("Customer", back_populates="contacts")
    cases = relationship("Case", back_populates="contact")
    survey_responses = relationship("SurveyResponse", back_populates="contact")

class Survey(Base):
    """SQLAlchemy model for storing survey information.
    
    This model represents a customer survey in the WiseCX system.
    
    Attributes:
        id (int): Primary key
        wise_id (str): WiseCX survey ID
        guid (str): Survey GUID
        name (str): Survey name
        created_at (datetime): Record creation timestamp
        updated_at (datetime): Record last update timestamp
        responses (List[SurveyResponse]): Related survey response records
    """
    
    __tablename__ = 'surveys'
    
    id = Column(Integer, primary_key=True)
    wise_id = Column(String(50), unique=True, nullable=False)
    guid = Column(String(50), unique=True, nullable=False)
    name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    responses = relationship("SurveyResponse", back_populates="survey")

class Case(Base):
    """Case model for storing case information.
    
    Attributes:
        id (int): Primary key
        case_id (str): WiseCX case ID
        group_id (str): Group ID
        number (str): Case number
        contact_id (str): Contact ID
        customer_id (str): Customer ID
        status (str): Case status
        tags (list): List of tags
        type_id (str): Type ID
        subject (str): Case subject
        priority (str): Case priority
        due_at (str): Due date
        custom_fields (dict): Custom fields
        created_at (datetime): Creation date
        solved_at (datetime): Solution date
        closed_at (datetime): Closing date
    """
    __tablename__ = 'cases'
    
    id = Column(Integer, primary_key=True)
    case_id = Column(String(50), unique=True, nullable=False)
    group_id = Column(String(50))
    number = Column(String(50))
    contact_id = Column(String(50), ForeignKey('contacts.wise_id'))
    customer_id = Column(String(50), ForeignKey('customers.wise_id'))
    status = Column(String(50))
    tags = Column(JSON)
    created_at = Column(DateTime)
    
    # Relationships
    contact = relationship("Contact", back_populates="cases")
    customer = relationship("Customer", back_populates="cases")
    survey_responses = relationship("SurveyResponse", back_populates="case")

class SurveyResponse(Base):
    """SQLAlchemy model for storing survey responses.
    
    This model represents a survey response associated with a case in the
    WiseCX system.
    
    Attributes:
        id (int): Primary key
        wise_id (str): Survey response ID
        survey_id (str): Survey ID
        case_id (int): Case ID
        contact_id (int): Contact ID
        responses (dict): JSON field containing:
            - responses: List of survey responses
            - responded_at: When the survey was responded
        created_at (datetime): Record creation timestamp
        updated_at (datetime): Record last update timestamp
        survey (Survey): Related survey record
        case (Case): Related case record
        contact (Contact): Related contact record
    """
    
    __tablename__ = 'survey_responses'
    
    id = Column(Integer, primary_key=True)
    wise_id = Column(String(50), unique=True, nullable=False)
    survey_id = Column(String(50), ForeignKey('surveys.wise_id'))
    case_id = Column(Integer, ForeignKey('cases.case_id'))
    contact_id = Column(Integer, ForeignKey('contacts.wise_id'))
    responses = Column(JSON)  # Array of {guid, response} objects
    responded_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    survey = relationship("Survey", back_populates="responses")
    case = relationship("Case", back_populates="survey_responses")
    contact = relationship("Contact", back_populates="survey_responses") 