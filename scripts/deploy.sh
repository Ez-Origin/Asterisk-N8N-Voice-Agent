#!/bin/bash

# Asterisk AI Voice Agent - Deployment Script
# This script deploys the application to the test server

set -e

# Configuration
SERVER="root@voiprnd.nemtclouddispatch.com"
PROJECT_DIR="/opt/asterisk-ai-voice-agent"
CONTAINER_NAME="asterisk-ai-voice-agent"

echo "🚀 Deploying Asterisk AI Voice Agent to test server..."

# Check if we're in the right directory
if [ ! -f "Dockerfile" ] || [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Push changes to Git
echo "📤 Pushing changes to Git..."
git add .
git commit -m "deploy: $(date '+%Y-%m-%d %H:%M:%S')" || echo "No changes to commit"
git push origin main

# Deploy to server
echo "🔄 Deploying to server..."
ssh $SERVER << EOF
    # Create project directory if it doesn't exist
    mkdir -p $PROJECT_DIR
    cd $PROJECT_DIR
    
    # Pull latest changes
    git clone https://github.com/haiderjarral/Asterisk-AI-Voice-Agent.git . || git pull origin main
    
    # Stop existing container
    docker-compose down || true
    
    # Build and start new container
    docker-compose up --build -d
    
    # Show container status
    docker-compose ps
    
    # Show logs
    echo "📋 Container logs:"
    docker-compose logs --tail=50
EOF

echo "✅ Deployment completed!"
echo "🔍 Check container status with: ssh $SERVER 'cd $PROJECT_DIR && docker-compose ps'"
echo "📋 View logs with: ssh $SERVER 'cd $PROJECT_DIR && docker-compose logs -f'"
