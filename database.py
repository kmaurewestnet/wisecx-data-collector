"""Database management for the WiseCX data collector."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Base, Contact, Survey, Case, SurveyResponse
from loguru import logger
import os
from dotenv import load_dotenv
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

load_dotenv()

# Datetime formats tried in order when parsing API timestamps
_DATETIME_FORMATS = [
    '%Y-%m-%dT%H:%M:%S.%fZ',   # 2023-12-01T15:30:45.123456Z
    '%Y-%m-%dT%H:%M:%SZ',       # 2023-12-01T15:30:45Z
    '%Y-%m-%dT%H:%M:%S.%f',     # 2023-12-01T15:30:45.123456
    '%Y-%m-%dT%H:%M:%S',        # 2023-12-01T15:30:45
    '%Y-%m-%d %H:%M:%S',        # 2023-12-01 15:30:45
    '%Y-%m-%d',                  # 2023-12-01
]


def _parse_datetime(value: str, label: str) -> Optional[datetime]:
    """Try parsing a datetime string with multiple formats. Returns None on failure."""
    if not value:
        return None
    # Python 3.11+ fromisoformat handles most ISO 8601 variants; use it as fast path
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
    except (ValueError, AttributeError):
        pass
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.warning(f"Could not parse datetime '{value}' for {label}")
    return None


class DatabaseManager:
    """Manages database operations for the WiseCX data collector."""

    def __init__(self) -> None:
        self.db_type = os.getenv('DB_TYPE', 'sqlite')

        if self.db_type == 'postgresql':
            self.connection_string = (
                f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
                f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
            )
            self.engine = create_engine(
                self.connection_string,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10
            )
        else:
            self.connection_string = 'sqlite:///wisecx_data.db'
            self.engine = create_engine(self.connection_string)

            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=10000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA mmap_size=30000000000")
                cursor.close()

        self.Session = scoped_session(sessionmaker(bind=self.engine))

    def init_db(self) -> None:
        """Create all tables."""
        Base.metadata.create_all(self.engine)
        logger.info("Database initialized successfully")

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate_contact_data(self, data: Dict[str, Any]) -> bool:
        return 'id' in data

    def _validate_survey_data(self, data: Dict[str, Any]) -> bool:
        return all(f in data for f in ('id', 'guid'))

    def _validate_case_data(self, data: Dict[str, Any]) -> bool:
        return 'id' in data

    def _validate_survey_response_data(self, data: Dict[str, Any]) -> bool:
        # Accept any of the known ID field names
        return any(data.get(f) is not None for f in ('id', 'response_id', 'survey_response_id'))

    # ── Save operations ───────────────────────────────────────────────────────

    def save_contact(self, contact_data: dict) -> Optional[Contact]:
        """Upsert a contact record."""
        if not self._validate_contact_data(contact_data):
            logger.error(f"Invalid contact data (missing 'id'): {contact_data}")
            return None

        wise_id = str(contact_data['id'])

        try:
            with self.session_scope() as session:
                contact = session.query(Contact).filter_by(wise_id=wise_id).first()

                last_update = _parse_datetime(contact_data.get('last_update'), f"contact {wise_id} last_update")

                params = {
                    'wise_id': wise_id,
                    'name': contact_data.get('name'),
                    'email': contact_data.get('email'),
                    'phone': contact_data.get('phone'),
                    'personal_id': contact_data.get('personal_id'),
                    'last_update': last_update,
                }

                if not contact:
                    contact = Contact(**params)
                    session.add(contact)
                    logger.info(f"Created contact {wise_id}")
                else:
                    for key, value in params.items():
                        if key != 'wise_id':
                            setattr(contact, key, value)
                    logger.info(f"Updated contact {wise_id}")

                session.flush()
                return contact

        except Exception as e:
            logger.error(f"Error saving contact {wise_id}: {str(e)}")
            return None

    def save_survey(self, survey_data: dict) -> Optional[Survey]:
        """Upsert a survey record."""
        if not self._validate_survey_data(survey_data):
            logger.error(f"Invalid survey data (missing 'id' or 'guid'): {survey_data}")
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
        """Upsert a case record."""
        if not self._validate_case_data(case_data):
            logger.error(f"Invalid case data (missing 'id'): {case_data}")
            return None

        case_id = str(case_data['id'])

        try:
            with self.session_scope() as session:
                case = session.query(Case).filter_by(case_id=case_id).first()

                created_at = _parse_datetime(case_data.get('created_at'), f"case {case_id} created_at")

                params = {
                    'case_id': case_id,
                    'group_id': case_data.get('group_id'),
                    'number': str(case_data.get('number')) if case_data.get('number') is not None else None,
                    'contact_id': str(case_data.get('contact_id')) if case_data.get('contact_id') else None,
                    'customer_id': str(case_data.get('customer_id')) if case_data.get('customer_id') else None,
                    'status': case_data.get('status'),
                    'tags': case_data.get('tags', []),
                }

                if not case:
                    params['created_at'] = created_at
                    case = Case(**params)
                    session.add(case)
                    logger.info(f"Created case {case_id}")
                else:
                    for key, value in params.items():
                        if key != 'case_id':
                            setattr(case, key, value)
                    # Preserve original created_at — never overwrite on updates
                    logger.info(f"Updated case {case_id}")

                session.flush()
                return case

        except Exception as e:
            logger.error(f"Error saving case {case_id}: {str(e)}")
            return None

    def save_survey_response(self, response_data: dict, survey_id: str) -> Optional[SurveyResponse]:
        """Upsert a survey response record."""
        if not self._validate_survey_response_data(response_data):
            logger.error(f"Invalid survey response data (missing id field): {list(response_data.keys())}")
            return None

        # Resolve ID from whichever field the API uses
        wise_id = None
        for field in ('id', 'response_id', 'survey_response_id'):
            if response_data.get(field) is not None:
                wise_id = str(response_data[field])
                break

        try:
            with self.session_scope() as session:
                record = session.query(SurveyResponse).filter_by(wise_id=wise_id).first()

                responded_at = _parse_datetime(
                    response_data.get('responded_at'), f"response {wise_id} responded_at"
                )

                # Normalise response content: try known field names in order
                raw = (
                    response_data.get('responses')
                    or response_data.get('answers')
                    or response_data.get('response')
                    or {}
                )
                if isinstance(raw, list):
                    # Convert [{guid, response}, ...] to {guid: response, ...}
                    responses = {
                        item['guid']: item.get('response', '')
                        for item in raw
                        if isinstance(item, dict) and 'guid' in item
                    }
                else:
                    responses = raw

                if not responses:
                    logger.warning(f"Skipping survey response {wise_id} - empty responses after normalisation")
                    return None

                case_id = str(response_data['case_id']) if response_data.get('case_id') else None
                contact_id = str(response_data['contact_id']) if response_data.get('contact_id') else None

                if not record:
                    record = SurveyResponse(
                        wise_id=wise_id,
                        survey_id=survey_id,
                        case_id=case_id,
                        contact_id=contact_id,
                        responses=responses,
                        responded_at=responded_at
                    )
                    session.add(record)
                else:
                    record.survey_id = survey_id
                    record.case_id = case_id
                    record.contact_id = contact_id
                    record.responses = responses
                    record.responded_at = responded_at

                session.flush()
                return record

        except Exception as e:
            logger.error(f"Error saving survey response {wise_id}: {str(e)}")
            return None

    def cleanup_old_data(self, days: int = 90) -> None:
        """Delete survey responses and cases older than `days` days.

        Survey responses are deleted first to avoid FK violations when
        removing their parent cases.
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            with self.session_scope() as session:
                # Delete responses whose cases are also old, to avoid FK violations
                # when cases with newer responses would otherwise be skipped.
                deleted_responses = (
                    session.query(SurveyResponse)
                    .filter(SurveyResponse.created_at < cutoff_date)
                    .delete(synchronize_session=False)
                )

                # Only delete cases that have no remaining (newer) survey responses
                old_case_ids = [
                    c.case_id for c in session.query(Case).filter(Case.created_at < cutoff_date).all()
                ]
                cases_with_responses = {
                    r.case_id
                    for r in session.query(SurveyResponse.case_id)
                    .filter(SurveyResponse.case_id.in_(old_case_ids))
                    .all()
                }
                safe_to_delete = [cid for cid in old_case_ids if cid not in cases_with_responses]
                deleted_cases = (
                    session.query(Case)
                    .filter(Case.case_id.in_(safe_to_delete))
                    .delete(synchronize_session=False)
                )

                logger.info(
                    f"Cleanup complete: removed {deleted_responses} responses "
                    f"and {deleted_cases} cases older than {days} days"
                )

        except Exception as e:
            logger.error(f"Error during data cleanup: {str(e)}")
            raise
