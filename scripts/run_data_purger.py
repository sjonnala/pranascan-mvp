import sys
import os
import logging
import asyncio

# Add the service-intelligence directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../service-intelligence')))

from app.database import AsyncSessionLocal
try:
    from app.services.data_purger_service import DataPurgerService
except ImportError:
    pass

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.StreamHandler(sys.stdout),
                        # You might want to add a FileHandler for production
                        # logging.FileHandler("data_purger.log")
                    ])
logger = logging.getLogger(__name__)

async def run_purger_job_async():
    db = None
    try:
        db = AsyncSessionLocal()
        if 'DataPurgerService' not in globals():
            logger.error("DataPurgerService could not be imported.")
            sys.exit(1)
        purger_service = DataPurgerService(db)
        # Attempt to run it async; fallback if it's sync
        if asyncio.iscoroutinefunction(purger_service.purge_old_deletion_requests):
            summary = await purger_service.purge_old_deletion_requests()
        else:
            summary = purger_service.purge_old_deletion_requests()
        logger.info(f"Data purging job completed. Summary: {summary}")
        await db.commit()
    except Exception as e:
        logger.critical(f"Unhandled error during data purging job: {e}", exc_info=True)
        if db:
            await db.rollback()
        sys.exit(1) # Exit with a non-zero code to indicate failure
    finally:
        if db:
            await db.close()

def run_purger_job():
    """
    Main function to run the data purging job.
    This script should be scheduled to run periodically (e.g., daily)
    by a cron job or other task scheduler.
    """
    asyncio.run(run_purger_job_async())
    sys.exit(0) # Exit successfully

if __name__ == "__main__":
    run_purger_job()
