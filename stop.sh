#!/bin/bash

# Anchor Project Shutdown Script
# Stops all running services

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🛑 Stopping Anchor services...${NC}\n"

# Stop Frontend
if [ -f pids/frontend.pid ]; then
    PID=$(cat pids/frontend.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo -e "${GREEN}✓ Frontend stopped${NC}"
    fi
    rm pids/frontend.pid
fi

# Stop Celery Worker
if [ -f pids/celery.pid ]; then
    PID=$(cat pids/celery.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo -e "${GREEN}✓ Celery Worker stopped${NC}"
    fi
    rm pids/celery.pid
fi

# Stop Backend API
if [ -f pids/backend.pid ]; then
    PID=$(cat pids/backend.pid)
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        echo -e "${GREEN}✓ Backend API stopped${NC}"
    fi
    rm pids/backend.pid
fi

# Stop Redis
if docker ps --filter "name=anchor-redis" --format "{{.Names}}" | grep -q anchor-redis; then
    docker stop anchor-redis >/dev/null 2>&1
    docker rm anchor-redis >/dev/null 2>&1
    echo -e "${GREEN}✓ Redis stopped${NC}"
fi

echo -e "\n${GREEN}✓ All services stopped${NC}\n"
