"""Database migration script for WiseCX data collector.

This script handles the migration of the database schema to support
the new data structure, particularly the changes in customer_id fields
and survey responses.
"""

from sqlalchemy import create_engine, text
from loguru import logger
import os
from dotenv import load_dotenv

load_dotenv()

def run_migration():
    """Run the database migration.
    
    This function:
    1. Creates a temporary column for customer_id
    2. Converts existing customer_id values to string
    3. Drops the old foreign key constraints
    4. Updates the column types
    5. Creates new foreign key constraints
    6. Cleans up temporary columns
    """
    try:
        # Create database connection
        connection_string = (
            f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@"
            f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        )
        engine = create_engine(connection_string)
        
        with engine.connect() as conn:
            # Start transaction
            with conn.begin():
                logger.info("Starting database migration...")
                
                # 1. Add temporary columns
                logger.info("Adding temporary columns...")
                conn.execute(text("""
                    ALTER TABLE contacts 
                    ADD COLUMN customer_id_new VARCHAR(50);
                """))
                
                conn.execute(text("""
                    ALTER TABLE surveys 
                    ADD COLUMN customer_id_new VARCHAR(50);
                """))
                
                # 2. Convert existing customer_id values to string
                logger.info("Converting customer_id values to string...")
                conn.execute(text("""
                    UPDATE contacts 
                    SET customer_id_new = CAST(customer_id AS VARCHAR);
                """))
                
                conn.execute(text("""
                    UPDATE surveys 
                    SET customer_id_new = CAST(customer_id AS VARCHAR);
                """))
                
                # 3. Drop old foreign key constraints
                logger.info("Dropping old foreign key constraints...")
                conn.execute(text("""
                    ALTER TABLE contacts 
                    DROP CONSTRAINT IF EXISTS contacts_customer_id_fkey;
                """))
                
                conn.execute(text("""
                    ALTER TABLE surveys 
                    DROP CONSTRAINT IF EXISTS surveys_customer_id_fkey;
                """))
                
                # 4. Update contacts table
                logger.info("Updating contacts table...")
                conn.execute(text("""
                    ALTER TABLE contacts 
                    DROP COLUMN customer_id;
                """))
                
                conn.execute(text("""
                    ALTER TABLE contacts 
                    ALTER COLUMN customer_id_new SET NOT NULL;
                """))
                
                conn.execute(text("""
                    ALTER TABLE contacts 
                    RENAME COLUMN customer_id_new TO customer_id;
                """))
                
                # 5. Update surveys table
                logger.info("Updating surveys table...")
                conn.execute(text("""
                    ALTER TABLE surveys 
                    DROP COLUMN customer_id;
                """))
                
                conn.execute(text("""
                    ALTER TABLE surveys 
                    ALTER COLUMN customer_id_new SET NOT NULL;
                """))
                
                conn.execute(text("""
                    ALTER TABLE surveys 
                    RENAME COLUMN customer_id_new TO customer_id;
                """))
                
                # 6. Create new foreign key constraints
                logger.info("Creating new foreign key constraints...")
                conn.execute(text("""
                    ALTER TABLE contacts 
                    ADD CONSTRAINT contacts_customer_id_fkey 
                    FOREIGN KEY (customer_id) 
                    REFERENCES customers(wise_id);
                """))
                
                conn.execute(text("""
                    ALTER TABLE surveys 
                    ADD CONSTRAINT surveys_customer_id_fkey 
                    FOREIGN KEY (customer_id) 
                    REFERENCES customers(wise_id);
                """))
                
                logger.info("Migration completed successfully!")
                
    except Exception as e:
        logger.error(f"Error during migration: {str(e)}")
        raise

if __name__ == "__main__":
    run_migration() 