#!/bin/bash
set -e

echo "🛑 Stopping Dora Multi-Agent System"

# Check if podman-compose is available
if ! command -v podman-compose &> /dev/null; then
    echo "❌ podman-compose is not installed. Please install podman-compose first."
    exit 1
fi

# Stop all services
echo "🔄 Stopping agent services..."
podman-compose -f docker-compose.agents.yml down

echo "🧹 Cleaning up stopped containers..."
podman container prune -f

echo "✅ All agent services stopped successfully"

# Show remaining containers (if any)
if podman ps -q | grep -q .; then
    echo ""
    echo "📋 Remaining containers:"
    podman ps --format "table {{.ID}}\t{{.Names}}\t{{.Status}}"
else
    echo ""
    echo "🎉 No containers running"
fi