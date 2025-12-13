# API Proxy Service

## Overview

The API Proxy Service is a flexible and scalable service designed to connect to third-party APIs using various protocols, including REST, WebSocket, MQTT, and Socket. Built with FastAPI, this service adheres to clean architecture principles and SOLID design principles, ensuring maintainability and extensibility.

## Features

- **Multi-Protocol Support**: Connects to third-party APIs using REST, WebSocket, MQTT, and Socket protocols.
- **Clean Architecture**: Organized codebase that separates concerns, making it easier to manage and extend.
- **Scalability**: Designed to handle a large number of users and requests efficiently.
- **Dependency Injection**: Utilizes dependency injection for better testability and modularity.
- **Logging and Error Handling**: Comprehensive logging and custom exception handling for improved observability.
- **Role-Based File Access**: Get files from current user and all child users based on role hierarchy.

## File Management Features

### File Upload and Query

The system provides comprehensive file management capabilities with role-based access control:

#### File Upload
- **Endpoint**: `POST /api/v1/files/upload`
- **Description**: Upload files with automatic deduplication based on file hash
- **Features**: 
  - Automatic file hashing for duplicate detection
  - Organized storage in year/month directories
  - Metadata storage in database
  - Support for custom field selection in response

#### File Query with User Hierarchy
- **Endpoint**: `POST /api/v1/files/my`
- **Description**: Query files with optional inclusion of child users' files
- **Parameters**:
  - `include_children`: Boolean flag to include files from current user and all child users
  - Standard pagination and filtering parameters
- **Role Hierarchy**: Automatically determines child users based on role parent_path structure

#### File Query with Children (Dedicated Endpoint)
- **Endpoint**: `POST /api/v1/files/my-with-children`
- **Description**: Specifically designed to get files from current user and all child users
- **Features**:
  - Always includes files from current user and all child users
  - Supports all standard query parameters (search, pagination, filtering)
  - Role-based access control based on user hierarchy

#### Usage Examples

**Get only current user's files:**
```json
POST /api/v1/files/my
{
  "table_name": "files",
  "page": 1,
  "page_size": 10,
  "include_children": false
}
```

**Get current user's files and all child users' files:**
```json
POST /api/v1/files/my
{
  "table_name": "files",
  "page": 1,
  "page_size": 10,
  "include_children": true
}
```

**Get files with children using dedicated endpoint:**
```json
POST /api/v1/files/my-with-children
{
  "table_name": "files",
  "page": 1,
  "page_size": 10,
  "search_text": "document",
  "search_fields": ["name"]
}
```

### Role Hierarchy Implementation

The file access system uses a role hierarchy based on the `parent_path` field in the roles table:

1. **Current User**: Files created by the authenticated user
2. **Child Users**: Users with roles that have the current user's role in their `parent_path`
3. **Hierarchy Traversal**: The system automatically finds all users in the hierarchy using SQL LIKE queries on the `parent_path` field

**Example Role Hierarchy:**
```
Role ID 1 (Admin) - parent_path: ",1,"
Role ID 2 (Manager) - parent_path: ",1,2,"
Role ID 3 (Employee) - parent_path: ",1,2,3,"
```

In this example, if a user has Role ID 1, they can access files from users with Role IDs 2 and 3.

## Dashboard and Statistics APIs

### Employee Performance Export

The system provides comprehensive employee performance export functionality with Excel file generation:

#### Employee Performance Export APIs
- **Endpoint**: `GET /api/v1/dashboard/employee-performance/export`
- **Description**: Export employee performance data to Excel file (no limit on number of users)
- **Parameters**:
  - `from_time`: Start time for the period (required)
  - `to_time`: End time for the period (required)

#### Weekly Export
- **Endpoint**: `GET /api/v1/dashboard/employee-performance/export/weekly`
- **Description**: Export employee performance for current week to Excel

#### Monthly Export
- **Endpoint**: `GET /api/v1/dashboard/employee-performance/export/monthly`
- **Description**: Export employee performance for current month to Excel

#### Quarterly Export
- **Endpoint**: `GET /api/v1/dashboard/employee-performance/export/quarterly`
- **Description**: Export employee performance for current quarter to Excel

#### Excel File Structure
The exported Excel file contains 3 beautifully formatted sheets:
1. **Báo cáo hiệu suất** - Main data with employee performance metrics
   - Professional title and headers with blue color scheme
   - Alternating row colors for better readability
   - Optimized column widths for perfect display
2. **Tóm tắt** - Summary statistics and performance categories
   - Clean sections with colored headers
   - Organized information display
   - Professional styling throughout
3. **Thống kê chi tiết** - Detailed analysis with top performers and distribution
   - Top 5 performers section
   - Performance distribution analysis
   - Consistent formatting with other sheets

#### Technical Features
- **Stable & Reliable**: Fixed MergedCell error for consistent operation
- **Professional Formatting**: Beautiful Excel styling with colors, borders, and fonts
- **Optimized Performance**: Efficient data processing and file generation
- **Error Handling**: Comprehensive error handling with fallback options

#### Usage Examples

**Export custom period:**
```bash
GET /api/v1/dashboard/employee-performance/export?from_time=2024-01-01T00:00:00&to_time=2024-01-31T23:59:59
```

**Export current week:**
```bash
GET /api/v1/dashboard/employee-performance/export/weekly
```

**Export current month:**
```bash
GET /api/v1/dashboard/employee-performance/export/monthly
```

**Export current quarter:**
```bash
GET /api/v1/dashboard/employee-performance/export/quarterly
```

### Task Work Statistics

The system provides comprehensive task work statistics with role-based access control:

#### User Period Statistics
- **Endpoint**: `GET /api/v1/dashboard/user-period-statistics`
- **Description**: Get task work statistics grouped by user and time period
- **Parameters**:
  - `from_date`: Start date for the statistics (required)
  - `to_date`: End date for the statistics (required)
  - `period`: Time period grouping - 'daily', 'monthly', 'quarterly' (default: 'daily')
  - `timezone`: Timezone for date grouping - 'Asia/Bangkok', 'UTC', etc. (default: 'Asia/Bangkok')

#### Daily Statistics
- **Endpoint**: `GET /api/v1/dashboard/user-daily-statistics`
- **Description**: Get daily task work statistics for each user for the last N days
- **Parameters**:
  - `days`: Number of days to analyze (1-365, default: 30)
  - `timezone`: Timezone for date grouping (default: 'Asia/Bangkok')

#### Monthly Statistics
- **Endpoint**: `GET /api/v1/dashboard/user-monthly-statistics`
- **Description**: Get monthly task work statistics for each user for the last N months
- **Parameters**:
  - `months`: Number of months to analyze (1-24, default: 12)
  - `timezone`: Timezone for date grouping (default: 'Asia/Bangkok')

#### Quarterly Statistics
- **Endpoint**: `GET /api/v1/dashboard/user-quarterly-statistics`
- **Description**: Get quarterly task work statistics for each user for the last N quarters
- **Parameters**:
  - `quarters`: Number of quarters to analyze (1-16, default: 8)
  - `timezone`: Timezone for date grouping (default: 'Asia/Bangkok')

#### Usage Examples

**Get daily statistics for the last 30 days (UTC+7):**
```bash
GET /api/v1/dashboard/user-daily-statistics?days=30
```

**Get monthly statistics for specific date range (UTC+7):**
```bash
GET /api/v1/dashboard/user-period-statistics?from_date=2024-01-01T00:00:00&to_date=2024-12-31T23:59:59&period=monthly
```

**Get quarterly statistics for the last 12 quarters (UTC+7):**
```bash
GET /api/v1/dashboard/user-quarterly-statistics?quarters=12
```

**Using different timezone (UTC):**
```bash
GET /api/v1/dashboard/user-daily-statistics?days=30&timezone=UTC
```

**Using different timezone (America/New_York):**
```bash
GET /api/v1/dashboard/user-period-statistics?from_date=2024-01-01T00:00:00&to_date=2024-01-31T23:59:59&period=daily&timezone=America/New_York
```

#### Response Format

All user period statistics APIs return data in the following format:

```json
{
  "user_statistics": [
    {
      "user_id": 1,
      "user_name": "Nguyễn Văn A",
      "user_email": "nguyenvana@example.com",
      "user_account": "nguyenvana",
      "periods": [
        {
          "period_start": "2024-01-01T00:00:00",
          "total_works": 5,
          "difficult_works": 2,
          "regular_works": 3
        }
      ],
      "total_works": 15,
      "total_difficult_works": 6,
      "total_regular_works": 9,
      "difficult_percentage": 40.0,
      "regular_percentage": 60.0
    }
  ],
  "summary": {
    "total_users": 5,
    "total_works": 75,
    "total_difficult_works": 25,
    "total_regular_works": 50,
    "difficult_percentage": 33.3,
    "average_works_per_user": 15.0
  },
  "period_info": {
    "from_date": "2024-01-01T00:00:00",
    "to_date": "2024-01-31T23:59:59",
    "period": "daily",
    "total_users_analyzed": 5
  }
}
```

#### Key Features

1. **Role Hierarchy Integration**: Automatically includes statistics from current user and all child users based on role hierarchy
2. **Period Grouping**: Supports daily, monthly, and quarterly grouping
3. **Detailed Statistics**: Provides total works, difficult works, regular works, and percentages for each user
4. **Summary Statistics**: Includes overall summary with averages and totals
5. **Flexible Date Ranges**: Supports custom date ranges and predefined periods
6. **Timezone Support**: Default Asia/Bangkok (UTC+7) with option to use other timezones

For more detailed information, see [USER_PERIOD_STATISTICS_API.md](USER_PERIOD_STATISTICS_API.md).

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Docker and Docker Compose (optional, for containerization)

### Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd api-proxy-service
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   - Copy `.env.example` to `.env` and fill in the required values.
   
   **Required Environment Variables:**
   ```bash
   # API Configuration
   BASE_URL=http://localhost:8000/api/v1
   
   # Database Configuration
   DATABASE_URI=postgresql+asyncpg://postgres:123456@localhost:5433/tms
   
   # JWT Configuration
   SECRET_KEY=your-secret-key-here
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=1440
   REFRESH_TOKEN_EXPIRE_DAYS=30
   
   # Redis Configuration
   REDIS_URL=redis://localhost:6379
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_DB=0
   REDIS_CELERY_DB=1
   
   # Logging
   LOG_LEVEL=INFO
   
   # Database Pool Settings
   DB_ECHO=false
   DB_POOL_SIZE=5
   DB_MAX_OVERFLOW=10
   ```

### Running the Application

To run the application, use the following command:
```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Running Tests

To run the tests, use:
```
pytest
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

### How to run the database migration

* Create or change models on a domain 

* Auto-generated migration from model
```
docker exec -it api-proxy-service-api-proxy-service-1 alembic revision --autogenerate -m "db-migrate"
```

* Migrate new model into database
```
docker exec -it api-proxy-service-api-proxy-service-1 alembic upgrade head
```

### Setup server deployment
1. Build and run docker compose

```
docker compose up
```

2. Run migration database

* Auto-generated migration from model
```
docker exec -it api-proxy-service-api-proxy-service-1 alembic revision --autogenerate -m "db-migrate"
```

* Migrate new model into database
```
docker exec -it api-proxy-service-api-proxy-service-1 alembic upgrade head
```

3. Đồng bộ data từ Netatmo về custom DB

```
docker exec -it api-proxy-service-api-proxy-service-1 bash
cd app/synchronizer/
python home_sync.py
python room_sync.py
python scenarios_sync.py
python schedule_sync.py
python module_sync.py
```

Lưu ý: khi chạy cần thay api_key tại `app/presentation/api/v1/endpoints/factory/netatmo_data_status_mock.py`

4. Test APIs tại: http://localhost:8000/docs




app
├── __init__.py
├── core
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── exceptions.py
│   ├── init_db.py
│   └── logger.py
├── domain
│   ├── __init__.py
│   ├── entities
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── device.py
│   │   └── netatmo_websocket_message.py
│   ├── interfaces
│   │   ├── __init__.py
│   │   ├── db_repository.py
│   │   ├── device_repository.py
│   │   ├── home_repository.py
│   │   ├── repositories.py
│   │   ├── room_repository.py
│   │   ├── scenarios_repository.py
│   │   ├── schedule_repository.py
│   │   └── services.py
│   └── models
│       ├── __init__.py
│       ├── associations
│       │   └── person_home_association.py
│       ├── device.py
│       ├── home.py
│       ├── module.py
│       ├── person.py
│       ├── room.py
│       ├── scenarios.py
│       ├── schedule.py
│       └── user.py
├── infrastructure
│   ├── __init__.py
│   ├── adapters
│   │   ├── __init__.py
│   │   └── websocket_adapter.py
│   ├── repositories
│   │   ├── __init__.py
│   │   ├── cache_repository.py                       # Redis Cacher 
│   │   ├── device_repository.py
│   │   ├── home_repository.py
│   │   ├── room_repository.py
│   │   ├── scenarios_repository.py
│   │   └── schedule_repository.py
│   └── services
│       ├── __init__.py
│       ├── auth_service.py
│       ├── celery_service.py
│       ├── proxy_service.py
│       └── websocket_service.py
├── main.py
├── presentation
│   ├── __init__.py
│   ├── api
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   └── v1
│   │       ├── __init__.py
│   │       ├── endpoints
│   │       │   ├── __init__.py
│   │       │   ├── factory
│   │       │   │   └── netatmo_data_status_mock.py
│   │       │   ├── internal                          
│   │       │   │   ├── home.py                       # Device Management: home, room, circuit
│   │       │   │   ├── room.py                       # Device Management: home, room, circuit
│   │       │   │   ├── scenarios.py                  # Scene, schedule Management
│   │       │   │   └── schedule.py                   # Scene, schedule Management
│   │       │   ├── mqtt_proxy.py
│   │       │   ├── netatmo_proxies                   # IOT Home Server Adapter
│   │       │   │   ├── auth_proxy.py                 # Netatmo Auth
│   │       │   │   ├── homedata_proxy.py
│   │       │   │   └── netatmo_router.py
│   │       │   ├── rest_proxy.py
│   │       │   ├── websocket_proxies                 # 2-ways Socket: Websocket 
│   │       │   │   └── websocket_proxy.py
│   │       │   └── websocket_proxy.py
│   │       ├── router.py                             # RESTful API Server
│   │       └── schemas
│   │           ├── __init__.py
│   │           ├── device.py
│   │           ├── home.py
│   │           ├── proxy_request.py
│   │           ├── room.py
│   │           ├── scenarios.py
│   │           └── schedule.py
│   └── middlewares
│       ├── __init__.py
│       ├── auth.py
│       └── logging.py
├── synchronizer                    # Asynchronous Task Manager
│   ├── home_sync.py
│   ├── module_sync.py
│   ├── room_sync.py
│   ├── scenarios_sync.py
│   └── schedule_sync.py
└── utils
    ├── __init__.py
    └── helpers.py
