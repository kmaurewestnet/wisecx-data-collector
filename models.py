"""Database models for the WiseCX data collector application."""

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class Customer(Base):
    __tablename__ = 'customers'

    id = Column(Integer, primary_key=True)
    wise_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(255))
    customer_number = Column(String(50))
    phone = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts = relationship("Contact", back_populates="customer")
    cases = relationship("Case", back_populates="customer")


class Contact(Base):
    __tablename__ = 'contacts'

    id = Column(Integer, primary_key=True)
    wise_id = Column(String(50), unique=True, nullable=False)
    customer_id = Column(String(50), ForeignKey('customers.wise_id'))
    name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    personal_id = Column(String(50))
    last_update = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="contacts")
    cases = relationship("Case", back_populates="contact")
    survey_responses = relationship("SurveyResponse", back_populates="contact")


class Survey(Base):
    __tablename__ = 'surveys'

    id = Column(Integer, primary_key=True)
    wise_id = Column(String(50), unique=True, nullable=False)
    guid = Column(String(50), unique=True, nullable=False)
    name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    responses = relationship("SurveyResponse", back_populates="survey")


class Case(Base):
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

    contact = relationship("Contact", back_populates="cases")
    customer = relationship("Customer", back_populates="cases")
    survey_responses = relationship("SurveyResponse", back_populates="case")


class SurveyResponse(Base):
    __tablename__ = 'survey_responses'

    id = Column(Integer, primary_key=True)
    wise_id = Column(String(50), unique=True, nullable=False)
    # FKs use String to match the referenced columns (wise_id / case_id are String(50))
    survey_id = Column(String(50), ForeignKey('surveys.wise_id'))
    case_id = Column(String(50), ForeignKey('cases.case_id'))
    contact_id = Column(String(50), ForeignKey('contacts.wise_id'))
    responses = Column(JSON)
    responded_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    survey = relationship("Survey", back_populates="responses")
    case = relationship("Case", back_populates="survey_responses")
    contact = relationship("Contact", back_populates="survey_responses")


# Explicit indexes on FK columns (SQLAlchemy does not create these automatically)
Index('ix_contacts_customer_id', Contact.customer_id)
Index('ix_cases_contact_id', Case.contact_id)
Index('ix_cases_customer_id', Case.customer_id)
Index('ix_survey_responses_survey_id', SurveyResponse.survey_id)
Index('ix_survey_responses_case_id', SurveyResponse.case_id)
Index('ix_survey_responses_contact_id', SurveyResponse.contact_id)
