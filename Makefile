.PHONY: dev dev-agent dev-ts dev-ts-full install install-web clean

# Run full stack with Python agent: Frontend + FastAPI backend + LangGraph agent
dev:
	@echo "Starting marlo-inbox full stack (Python agent)..."
	@echo "Frontend will open at http://localhost:5173"
	@trap 'kill 0' EXIT; \
	(cd py-inbox && uvicorn app.main:app --reload --port 8000) & \
	(langgraph dev --no-browser) & \
	(cd web && npm run dev) & \
	wait

# Run full stack with TypeScript agent: Frontend + FastAPI backend + TS LangGraph
dev-ts-full:
	@echo "Starting marlo-inbox full stack (TypeScript agent)..."
	@echo "Frontend will open at http://localhost:5173"
	@trap 'kill 0' EXIT; \
	(cd py-inbox && uvicorn app.main:app --reload --port 8000) & \
	(cd ts-inbox && langgraph dev --no-browser) & \
	(cd web && npm run dev) & \
	wait

# Run just Python LangGraph agent (for testing with LangSmith Studio)
dev-agent:
	langgraph dev

# Run backend only (FastAPI + Python LangGraph)
dev-backend:
	@echo "Starting backend services..."
	@trap 'kill 0' EXIT; \
	(cd py-inbox && uvicorn app.main:app --reload --port 8000) & \
	(langgraph dev) & \
	wait

# Run TypeScript LangGraph agent only (for testing with LangSmith Studio)
dev-ts:
	cd ts-inbox && langgraph dev

# Install Python dependencies
install:
	pip install -e .

# Install frontend dependencies
install-web:
	cd web && npm install

# Install TypeScript dependencies
install-ts:
	cd ts-inbox && npm install

# Install all dependencies
install-all: install install-web install-ts

# Clean up
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
