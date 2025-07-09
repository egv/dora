#!/bin/bash
set -e

echo "🚀 Starting Dora Multi-Agent System with Podman"

# Check if podman is available
if ! command -v podman &> /dev/null; then
    echo "❌ Podman is not installed. Please install podman first."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Build and start all services
echo "🏗️  Building agent containers..."
podman-compose -f docker-compose.agents.yml build

echo "🚀 Starting agent services..."
podman-compose -f docker-compose.agents.yml up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service health
echo "🔍 Checking service health..."

# Check EventSearchAgent
if curl -f http://localhost:8001/health >/dev/null 2>&1; then
    echo "✅ EventSearchAgent is healthy"
else
    echo "❌ EventSearchAgent is not responding"
fi

# Check CalendarIntelligenceAgent  
if curl -f http://localhost:8002/health >/dev/null 2>&1; then
    echo "✅ CalendarIntelligenceAgent is healthy"
else
    echo "❌ CalendarIntelligenceAgent is not responding"
fi

# Check Redis
if podman exec dora-redis redis-cli ping >/dev/null 2>&1; then
    echo "✅ Redis is healthy"
else
    echo "❌ Redis is not responding"
fi

# Check PostgreSQL
if podman exec dora-postgres pg_isready -U dora >/dev/null 2>&1; then
    echo "✅ PostgreSQL is healthy"
else
    echo "❌ PostgreSQL is not responding"
fi

echo ""
echo "🎉 Multi-agent system is ready!"
echo ""
echo "📍 Service endpoints:"
echo "   • EventSearchAgent: http://localhost:8001"
echo "   • CalendarIntelligenceAgent: http://localhost:8002" 
echo "   • Redis: localhost:6379"
echo "   • PostgreSQL: localhost:5432"
echo ""
echo "🔍 Health checks:"
echo "   • EventSearchAgent: curl http://localhost:8001/health"
echo "   • CalendarIntelligenceAgent: curl http://localhost:8002/health"
echo ""
echo "📋 To view logs:"
echo "   podman-compose -f docker-compose.agents.yml logs -f"
echo ""
echo "🛑 To stop all services:"
echo "   podman-compose -f docker-compose.agents.yml down"