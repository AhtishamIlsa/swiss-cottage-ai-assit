# Nginx Configuration for Swiss Cottage AI Assistant

This directory contains nginx configuration and setup scripts for deploying the Swiss Cottage AI Assistant.

## Files

- `swiss-cottage-ai.conf` - Main nginx configuration file
- `setup_nginx.sh` - Automated setup script
- `systemd/` - Systemd service files for production deployment

## Quick Start

### 1. Run the Setup Script

```bash
sudo ./nginx/setup_nginx.sh
```

### 2. Start Your Applications

**Terminal 1 - FastAPI:**
```bash
./run_api.sh
```

**Terminal 2 - Streamlit:**
```bash
./run_rag_chatbot.sh
```

### 3. Access Your Site

- **Streamlit UI**: http://localhost/
- **API**: http://localhost/api/
- **API Docs**: http://localhost/docs

## Optional: Systemd Services

For production, you can run the applications as systemd services:

```bash
sudo ./nginx/systemd/install_services.sh
sudo systemctl start swiss-cottage-api
sudo systemctl start swiss-cottage-streamlit
```

## Documentation

See `../NGINX_DEPLOYMENT.md` for detailed documentation including:
- Manual setup instructions
- SSL/HTTPS configuration
- Domain configuration
- Troubleshooting
- Performance tuning
