#!/bin/bash

# Anchor Project Startup Script
# Starts all required services: Redis, Backend API, Celery Worker, and Frontend

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🎬 Starting Anchor Video Platform...${NC}\n"

# Check if Redis is already running
if lsof -Pi :6379 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${GREEN}✓ Redis already running on port 6379${NC}"
else
    echo -e "${BLUE}Starting Redis...${NC}"
    docker run -d -p 6379:6379 --name anchor-redis redis:alpine
    echo -e "${GREEN}✓ Redis started${NC}"
fi

# Start Backend API
echo -e "\n${BLUE}Starting Backend API...${NC}"
cd backend
uv sync
(uv run uvicorn main:app --reload > ../logs/backend.log 2>&1 &)
echo $! > ../pids/backend.pid
echo -e "${GREEN}✓ Backend API started (PID: $(cat ../pids/backend.pid))${NC}"

# Start Celery Worker
echo -e "\n${BLUE}Starting Celery Worker...${NC}"
(uv run celery -A worker worker --loglevel=info > ../logs/celery.log 2>&1 &)
echo $! > ../pids/celery.pid
echo -e "${GREEN}✓ Celery Worker started (PID: $(cat ../pids/celery.pid))${NC}"
cd ..

# Start Frontend
echo -e "\n${BLUE}Starting Frontend...${NC}"
cd frontend
bun install
(bun dev > ../logs/frontend.log 2>&1 &)
echo $! > ../pids/frontend.pid
echo -e "${GREEN}✓ Frontend started (PID: $(cat ../pids/frontend.pid))${NC}"
cd ..

echo -e "\n${GREEN}🚀 All services started successfully!${NC}\n"
echo -e "Access points:"
echo -e "  Frontend:  ${BLUE}http://localhost:3000${NC}"
echo -e "  Backend:   ${BLUE}http://localhost:8000${NC}"
echo -e "  API Docs:  ${BLUE}http://localhost:8000/docs${NC}"
echo -e "  Redis:     ${BLUE}localhost:6379${NC}"
echo -e "\nLogs available in ./logs/"
echo -e "To stop all services, run: ${BLUE}./stop.sh${NC}\n"
