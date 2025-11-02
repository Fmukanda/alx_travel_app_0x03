# Starting Celery with RabbitMQ

```
# Start Celery worker for all queues
celery -A your_project worker --loglevel=info --concurrency=4

# Or start worker for specific queues
celery -A your_project worker --loglevel=info --queues=emails,celery --concurrency=2

# Start Celery beat for periodic tasks (if needed)
celery -A your_project beat --loglevel=info

# Start Flower for monitoring
celery -A your_project flower --port=5555
8. Testing RabbitMQ Connection
Create a test script to verify the setup:
````

python
```
# test_celery_setup.py
import os
import django
from celery import current_app

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
django.setup()

def test_celery_connection():
    try:
        # Test Celery app
        insp = current_app.control.inspect()
        stats = insp.stats()
        print("✅ Celery workers connected:", bool(stats))
        
        # Test broker connection
        from kombu import Connection
        with Connection('amqp://localhost:5672//') as conn:
            conn.ensure_connection(max_retries=3)
            print("✅ RabbitMQ connection successful")
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == '__main__':
    test_celery_connection()
```

## Monitoring RabbitMQ
```
# Check RabbitMQ status
sudo rabbitmqctl status

# List queues
sudo rabbitmqctl list_queues

# List connections
sudo rabbitmqctl list_connections

# Monitor via management plugin (enable first)
sudo rabbitmq-plugins enable rabbitmq_management

# Then visit http://localhost:15672 (guest/guest)
```

## Key Updates for RabbitMQ Compatibility:
 - **Proper Broker URL:** Using amqp:// protocol for RabbitMQ
 - **Task Retry Logic:** Added retry mechanisms with exponential backoff
 - **Error Handling:** Comprehensive exception handling and logging
 - **Queue Routing:** Optional task routing to different queues
 - **Connection Management:** Proper connection pooling and recovery
 - **Result Backend:** Using RPC backend suitable for RabbitMQ
 - **Task Bindings:** Using bind=True for access to task instance methods
