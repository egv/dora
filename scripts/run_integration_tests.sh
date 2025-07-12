#!/bin/bash

# Script to run database integration tests
# This script sets up a test database environment and runs integration tests

set -e

echo "🚀 Setting up database integration tests..."

# Check if Docker/Podman is available
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
elif command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
else
    echo "❌ Error: Neither podman nor docker is available"
    echo "Please install podman or docker to run integration tests"
    exit 1
fi

echo "📦 Using container runtime: $CONTAINER_CMD"

# Database configuration
DB_NAME="dora_test"
DB_USER="dora"
DB_PASSWORD="dora_test_password"
DB_PORT="5433"
REDIS_PORT="6380"

# Check if containers are already running
if $CONTAINER_CMD ps --format "table {{.Names}}" | grep -q "dora-test-postgres\|dora-test-redis"; then
    echo "🔄 Stopping existing test containers..."
    $CONTAINER_CMD stop dora-test-postgres dora-test-redis || true
    $CONTAINER_CMD rm dora-test-postgres dora-test-redis || true
fi

echo "🐘 Starting PostgreSQL test container..."
$CONTAINER_CMD run -d \
    --name dora-test-postgres \
    -e POSTGRES_DB=$DB_NAME \
    -e POSTGRES_USER=$DB_USER \
    -e POSTGRES_PASSWORD=$DB_PASSWORD \
    -p $DB_PORT:5432 \
    postgres:15-alpine

echo "📦 Starting Redis test container..."
$CONTAINER_CMD run -d \
    --name dora-test-redis \
    -p $REDIS_PORT:6379 \
    redis:7-alpine

echo "⏳ Waiting for databases to be ready..."
sleep 5

# Wait for PostgreSQL to be ready
echo "🔍 Checking PostgreSQL connection..."
for i in {1..30}; do
    if $CONTAINER_CMD exec dora-test-postgres pg_isready -U $DB_USER > /dev/null 2>&1; then
        echo "✅ PostgreSQL is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ PostgreSQL failed to start"
        exit 1
    fi
    sleep 1
done

# Wait for Redis to be ready
echo "🔍 Checking Redis connection..."
for i in {1..30}; do
    if $CONTAINER_CMD exec dora-test-redis redis-cli ping | grep -q PONG; then
        echo "✅ Redis is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Redis failed to start"
        exit 1
    fi
    sleep 1
done

echo "🗄️ Initializing database schema..."
$CONTAINER_CMD exec -i dora-test-postgres psql -U $DB_USER -d $DB_NAME < scripts/init_db.sql

# Set environment variables for tests
export TEST_DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@localhost:$DB_PORT/$DB_NAME"
export TEST_REDIS_URL="redis://localhost:$REDIS_PORT/1"
export RUN_INTEGRATION_TESTS=1

echo "🧪 Running integration tests..."
echo "Database URL: $TEST_DATABASE_URL"
echo "Redis URL: $TEST_REDIS_URL"

# Run the integration tests
if uv run python -m pytest tests/test_database_integration.py -v --tb=short; then
    echo "✅ All integration tests passed!"
    TEST_RESULT=0
else
    echo "❌ Some integration tests failed"
    TEST_RESULT=1
fi

echo "🧹 Cleaning up test containers..."
$CONTAINER_CMD stop dora-test-postgres dora-test-redis
$CONTAINER_CMD rm dora-test-postgres dora-test-redis

if [ $TEST_RESULT -eq 0 ]; then
    echo "🎉 Integration tests completed successfully!"
else
    echo "💥 Integration tests failed"
    exit 1
fi