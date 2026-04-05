import sys
import os
import logging

# Add the backend directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.database import SessionLocal
from app.services.data_purger_service import DataPurgerService

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.StreamHandler(sys.stdout),
                        # You might want to add a FileHandler for production
                        # logging.FileHandler("data_purger.log")
                    ])
logger = logging.getLogger(__name__)

def run_purger_job():
    """
    Main function to run the data purging job.
    This script should be scheduled to run periodically (e.g., daily)
    by a cron job or other task scheduler.
    """
    db = None
    try:
        db = SessionLocal()
        purger_service = DataPurgerService(db)
        summary = purger_service.purge_old_deletion_requests()
        logger.info(f"Data purging job completed. Summary: {summary}")
    except Exception as e:
        logger.critical(f"Unhandled error during data purging job: {e}", exc_info=True)
        if db:
            db.rollback()
        sys.exit(1) # Exit with a non-zero code to indicate failure
    finally:
        if db:
            db.close()
    sys.exit(0) # Exit successfully

if __name__ == "__main__":
    run_purger_job()
