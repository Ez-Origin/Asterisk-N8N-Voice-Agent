# Makefile for the Asterisk AI Voice Agent

# Default values - can be overridden from the command line
SERVER_USER := root
SERVER_HOST := voiprnd.nemtclouddispatch.com
PROJECT_PATH := /root/Asterisk-Agent-Develop
SERVICE ?= ai-engine
provider ?= local

# ==============================================================================
# LOCAL DEVELOPMENT
# ==============================================================================

## build: Build or rebuild all service images
build:
	docker-compose build

## up: Start all services in the background
up:
	docker-compose up -d

## down: Stop and remove all services
down:
	docker-compose down --remove-orphans

## logs: Tail the logs of a specific service (default: ai-engine)
logs:
	docker-compose logs -f $(SERVICE)

## logs-all: Tail the logs of all services
logs-all:
	docker-compose logs -f

## ps: Show the status of running services
ps:
	docker-compose ps

## model-setup: Detect host tier, download required local provider models, and skip if cached
model-setup:
	python3 scripts/model_setup.py --assume-yes

# ==============================================================================
# DEPLOYMENT & SERVER MANAGEMENT
# ==============================================================================

## deploy: Pull latest code and deploy the ai-engine on the server (with --no-cache)
deploy:
	@echo "--> Deploying latest code to $(SERVER_HOST) with --no-cache..."
	@echo "⚠️  WARNING: This will deploy uncommitted changes if any exist!"
	@echo "   Use 'make deploy-safe' for validation, or 'make deploy-force' to skip checks"
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && git pull && docker-compose build --no-cache ai-engine && docker-compose up -d ai-engine'

## deploy-safe: Validate changes are committed before deploying
deploy-safe:
	@echo "--> Safe deployment with validation..."
	@echo "🔍 Checking for uncommitted changes..."
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "❌ ERROR: You have uncommitted changes!"; \
		echo "   Please commit your changes first:"; \
		echo "   git add . && git commit -m 'Your commit message'"; \
		echo "   Or use 'make deploy-force' to skip this check"; \
		exit 1; \
	fi
	@echo "✅ No uncommitted changes found"
	@echo "🚀 Pushing changes to remote..."
	git push origin develop
	@echo "⏳ Waiting 5 seconds for remote propagation..."
	sleep 5
	@echo "🔍 Verifying remote has latest commit..."
	@make verify-remote-sync
	@echo "📦 Deploying to server with --no-cache..."
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && git pull && docker-compose build --no-cache ai-engine && docker-compose up -d ai-engine'
	@echo "🔍 Verifying server has latest commit..."
	@make verify-server-commit
	@echo "🔍 Verifying deployment..."
	@make verify-deployment

## deploy-force: Deploy without validation (use with caution)
deploy-force:
	@echo "--> Force deployment (skipping validation)..."
	@echo "⚠️  WARNING: This will deploy even with uncommitted changes!"
	@echo "⏳ Waiting 5 seconds before deployment..."
	sleep 5
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && git pull && docker-compose build --no-cache ai-engine && docker-compose up -d ai-engine'
	@echo "🔍 Verifying server has latest commit..."
	@make verify-server-commit
	@echo "🔍 Verifying deployment..."
	@make verify-deployment

## deploy-full: Pull latest and rebuild all services on the server
deploy-full:
	@echo "--> Performing a full rebuild and deployment on $(SERVER_HOST)..."
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && git pull && docker-compose up --build -d'

## deploy-no-cache: Pull latest and force a no-cache rebuild of ai-engine
deploy-no-cache:
	@echo "--> Forcing a no-cache rebuild and deployment of ai-engine on $(SERVER_HOST)..."
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && git pull && docker-compose build --no-cache ai-engine && docker-compose up -d ai-engine'

## server-logs: View live logs for a service on the server (follow mode - use Ctrl+C to exit)
server-logs:
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs -f $(SERVICE)'

## server-logs-snapshot: View last N lines of logs and exit (default: 50)
server-logs-snapshot:
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --tail=$(LINES) $(SERVICE)'

## server-status: Check the status of services on the server
server-status:
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose ps'

## server-clear-logs: Truncate Docker logs on server and restart containers
server-clear-logs:
	@echo "--> Truncating Docker container logs on $(SERVER_HOST)..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'sudo sh -c "truncate -s 0 /var/lib/docker/containers/*/*-json.log"'
	@echo "--> Restarting ai-engine and local-ai-server containers..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker restart local_ai_server && sleep 10 && docker restart ai_engine'
	@echo "✅ Server logs cleared and containers restarted"

## server-capture-logs: Capture full logs from server containers into timestamped files
server-capture-logs:
	@echo "--> Capturing ai-engine logs to logs/ai-engine-$$(date +%Y%m%d-%H%M%S).log"
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --no-color ai-engine' > logs/ai-engine-$$(date +%Y%m%d-%H%M%S).log
	@echo "--> Capturing local-ai-server logs to logs/local-ai-server-$$(date +%Y%m%d-%H%M%S).log"
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --no-color local-ai-server' > logs/local-ai-server-$$(date +%Y%m%d-%H%M%S).log

## server-health: Check deployment health (ARI, ExternalMedia, Providers)
server-health:
	@echo "--> Checking deployment health on $(SERVER_HOST)..."
	@echo "🔍 Checking ARI connections..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --tail=200 ai-engine | grep -E "(Successfully connected to ARI HTTP endpoint|Successfully connected to ARI WebSocket)" || echo "❌ ARI connection issues"'
	@echo "🔍 Checking RTP server..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --tail=200 ai-engine | grep -E "(RTP server started|RTP server listening)" || echo "❌ RTP server issues"'
	@echo "🔍 Checking provider loading..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --tail=200 ai-engine | grep -E "(Provider.*loaded successfully|Default provider.*is available)" || echo "❌ Provider loading issues"'
	@echo "🔍 Checking engine status..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --tail=200 ai-engine | grep -E "(Engine started and listening for calls)" || echo "❌ Engine startup issues"'
	@echo "✅ Health check complete"

# ==============================================================================
# TESTING & VERIFICATION
# ==============================================================================

## test-local: Run local tests
test-local:
	docker-compose exec ai-engine python /app/test_ai_engine.py
	docker-compose exec local-ai-server python /app/test_local_ai_server.py

## test-integration: Run integration tests
test-integration:
	docker-compose exec ai-engine python /app/test_integration.py

## test-ari: Test ARI commands
test-ari:
	ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose exec ai-engine python /app/test_ari_commands.py'

## test-externalmedia: Test ExternalMedia + RTP implementation
test-externalmedia:
	@echo "--> Testing ExternalMedia + RTP implementation..."
	python3 scripts/validate_externalmedia_config.py
	python3 scripts/test_externalmedia_call.py

## test-health: Check the local health endpoint (defaults to http://127.0.0.1:15000/health)
test-health:
	@HEALTH_URL=$${HEALTH_URL:-http://127.0.0.1:15000/health}; \
	echo "--> Checking $$HEALTH_URL"; \
	if ! curl -sS $$HEALTH_URL ; then \
		echo "❌ Health check failed"; \
		exit 1; \
	else \
		echo "✅ Health check succeeded"; \
	fi

## quick-regression: Run health check and print manual call checklist
quick-regression:
	@$(MAKE) --no-print-directory test-health
	@echo
	@echo "Next steps:" \
	  && echo "1. Clear logs (local: make logs --tail=0 ai-engine | remote: make server-clear-logs)." \
	  && echo "2. Place a short call into the AI context." \
	  && echo "3. Watch for ExternalMedia bridge join, RTP frames, provider input, playback start/finish, and cleanup." \
	  && echo "4. Re-run make test-health to ensure active_calls resets to 0." \
	  && echo "5. Capture findings in call-framework.md or your issue tracker."

## provider-switch: Update default provider locally
provider-switch:
	@if [ -z "$(provider)" ]; then \
		echo "Usage: make provider=<name> provider-switch"; \
		exit 1; \
	fi
	@python3 scripts/switch_provider.py --config config/ai-agent.yaml --provider $(provider)

## provider-switch-remote: Update default provider on the server
provider-switch-remote:
	@if [ -z "$(provider)" ]; then \
		echo "Usage: make provider=<name> provider-switch-remote"; \
		exit 1; \
	fi
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose exec -T ai-engine python /app/scripts/switch_provider.py --config /app/config/ai-agent.yaml --provider $(provider)'

## provider-reload: Switch provider on server, restart ai-engine, and run health check
provider-reload:
	@$(MAKE) --no-print-directory provider-switch-remote provider=$(provider)
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose up -d ai-engine'
	@$(MAKE) --no-print-directory server-health

## verify-deployment: Verify that deployment was successful
verify-deployment:
	@echo "🔍 Verifying deployment..."
	@echo "📊 Checking container status..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose ps'
	@echo "📋 Checking recent logs for errors..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --tail=10 ai-engine | grep -E "(ERROR|CRITICAL|Exception|Traceback)" || echo "✅ No errors found in recent logs"'
	@echo "⚙️  Checking configuration..."
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && docker-compose logs --tail=20 ai-engine | grep -E "(audio_transport|RTP Server|ExternalMedia)" || echo "⚠️  Configuration logs not found"'
	@echo "✅ Deployment verification complete"

## verify-remote-sync: Verify that remote repository has the latest commit
verify-remote-sync:
	@echo "🔍 Verifying remote repository sync..."
	@echo "📋 Getting local commit hash..."
	@LOCAL_COMMIT=$$(git rev-parse HEAD); \
	echo "Local commit: $$LOCAL_COMMIT"; \
	echo "📋 Getting remote commit hash..."; \
	REMOTE_COMMIT=$$(git ls-remote origin develop | cut -f1); \
	echo "Remote commit: $$REMOTE_COMMIT"; \
	if [ "$$LOCAL_COMMIT" = "$$REMOTE_COMMIT" ]; then \
		echo "✅ Remote repository is in sync with local"; \
	else \
		echo "❌ ERROR: Remote repository is not in sync!"; \
		echo "   Local:  $$LOCAL_COMMIT"; \
		echo "   Remote: $$REMOTE_COMMIT"; \
		echo "   Waiting 5 more seconds and retrying..."; \
		sleep 5; \
		REMOTE_COMMIT=$$(git ls-remote origin develop | cut -f1); \
		if [ "$$LOCAL_COMMIT" = "$$REMOTE_COMMIT" ]; then \
			echo "✅ Remote repository is now in sync"; \
		else \
			echo "❌ ERROR: Remote repository still not in sync after retry!"; \
			exit 1; \
		fi; \
	fi

## verify-server-commit: Verify that server has the expected commit
verify-server-commit:
	@echo "🔍 Verifying server has the latest commit..."
	@echo "📋 Getting local commit hash..."
	@LOCAL_COMMIT=$$(git rev-parse HEAD); \
	echo "Local commit: $$LOCAL_COMMIT"; \
	echo "📋 Getting server commit hash..."; \
	SERVER_COMMIT=$$(ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && git rev-parse HEAD'); \
	echo "Server commit: $$SERVER_COMMIT"; \
	if [ "$$LOCAL_COMMIT" = "$$SERVER_COMMIT" ]; then \
		echo "✅ Server has the latest commit"; \
	else \
		echo "❌ ERROR: Server does not have the latest commit!"; \
		echo "   Local:  $$LOCAL_COMMIT"; \
		echo "   Server: $$SERVER_COMMIT"; \
		exit 1; \
	fi

## verify-config: Verify the configuration is correct
verify-config:
	@echo "🔍 Verifying configuration..."
	@echo "📋 Local configuration:"
	@python3 scripts/validate_externalmedia_config.py
	@echo "📋 Server configuration:"
	@ssh $(SERVER_USER)@$(SERVER_HOST) 'cd $(PROJECT_PATH) && python3 scripts/validate_externalmedia_config.py'

## monitor-externalmedia: Monitor ExternalMedia + RTP status
monitor-externalmedia:
	@echo "--> Starting ExternalMedia + RTP monitoring..."
	python3 scripts/monitor_externalmedia.py

## monitor-externalmedia-once: Check ExternalMedia + RTP status once
monitor-externalmedia-once:
	@echo "--> Checking ExternalMedia + RTP status..."
	python3 scripts/monitor_externalmedia.py --once

## capture-logs: Capture structured logs during test call (default: 40 seconds)
capture-logs:
	@echo "--> Starting structured log capture for test call..."
	@echo "📞 Make your test call now!"
	python3 scripts/capture_test_logs.py --duration 40

## capture-logs-short: Capture logs for 30 seconds
capture-logs-short:
	@echo "--> Starting 30-second log capture..."
	@echo "📞 Make your test call now!"
	python3 scripts/capture_test_logs.py --duration 30

## capture-logs-long: Capture logs for 60 seconds
capture-logs-long:
	@echo "--> Starting 60-second log capture..."
	@echo "📞 Make your test call now!"
	python3 scripts/capture_test_logs.py --duration 60

## analyze-logs: Analyze the most recent captured logs
analyze-logs:
	@echo "--> Analyzing most recent test call logs..."
	@if [ -d "logs" ] && [ "$$(ls -A logs/*.json 2>/dev/null)" ]; then \
		LATEST_LOG=$$(ls -t logs/*.json | head -1); \
		echo "📊 Analyzing: $$LATEST_LOG"; \
		python3 scripts/analyze_logs.py "$$LATEST_LOG"; \
	else \
		echo "❌ No log files found in logs/ directory"; \
	fi

## test-call: Complete test call workflow (capture + analyze)
test-call:
	@echo "--> Starting complete test call workflow..."
	@echo "📞 Make your test call now!"
	@echo "⏱️  Capturing logs for 40 seconds..."
	python3 scripts/capture_test_logs.py --duration 40
	@echo "🔍 Analyzing captured logs..."
	@if [ -d "logs" ] && [ "$$(ls -A logs/*.json 2>/dev/null)" ]; then \
		LATEST_LOG=$$(ls -t logs/*.json | head -1); \
		LATEST_FRAMEWORK=$$(ls -t logs/*.md | head -1); \
		echo "📊 Analysis complete!"; \
		echo "📁 JSON logs: $$LATEST_LOG"; \
		echo "📋 Framework analysis: $$LATEST_FRAMEWORK"; \
		echo "🔍 View framework analysis:"; \
		echo "   cat $$LATEST_FRAMEWORK"; \
	fi

# ==============================================================================
# UTILITIES & HELP
# ==============================================================================

## help: Show this help message
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: build up down logs logs-all ps deploy deploy-safe deploy-force deploy-full deploy-no-cache server-logs server-logs-snapshot server-status server-clear-logs server-health test-local test-integration test-ari test-externalmedia verify-deployment verify-remote-sync verify-server-commit verify-config monitor-externalmedia monitor-externalmedia-once help
