# WordPress Integration Guide

This guide explains how to integrate the Swiss Cottages Chatbot widget into your WordPress site.

## Overview

The chatbot widget is a JavaScript widget that can be embedded in WordPress with a single script tag. It automatically creates a floating chat button and chat window that communicates with the FastAPI backend.

## Prerequisites

1. FastAPI server running (see `run_api.sh`)
2. WordPress site with ability to add custom HTML/scripts
3. API server accessible from WordPress domain (CORS configured)

## Integration Methods

### Method 1: Header Script Tag (Recommended)

Add the following code to your WordPress theme's `header.php` file or use a plugin that allows custom header scripts:

```html
<!-- Swiss Cottages Chatbot Widget -->
<script src="http://your-api-server:8000/static/js/chatbot-widget.js"></script>
<link rel="stylesheet" href="http://your-api-server:8000/static/css/chatbot-widget.css">
```

**Replace `your-api-server:8000` with your actual API server URL.**

### Method 2: WordPress Plugin

Create a simple WordPress plugin:

1. Create a new file: `wp-content/plugins/swiss-cottages-chatbot/swiss-cottages-chatbot.php`

```php
<?php
/**
 * Plugin Name: Swiss Cottages Chatbot
 * Description: Adds Swiss Cottages chatbot widget to your site
 * Version: 1.0.0
 * Author: Your Name
 */

function swiss_cottages_chatbot_enqueue_scripts() {
    $api_url = get_option('swiss_cottages_api_url', 'http://localhost:8000');
    
    wp_enqueue_script(
        'swiss-cottages-chatbot',
        $api_url . '/static/js/chatbot-widget.js',
        array(),
        '1.0.0',
        true
    );
    
    wp_enqueue_style(
        'swiss-cottages-chatbot',
        $api_url . '/static/css/chatbot-widget.css',
        array(),
        '1.0.0'
    );
}
add_action('wp_enqueue_scripts', 'swiss_cottages_chatbot_enqueue_scripts');
```

2. Activate the plugin in WordPress admin

### Method 3: CDN Hosting

For better performance, upload the widget files to a CDN:

1. Upload `chatbot/static/js/chatbot-widget.js` and `chatbot/static/css/chatbot-widget.css` to your CDN
2. Update the script and link tags to point to CDN URLs

## Configuration Options

You can customize the widget using data attributes on the script tag:

```html
<script 
    src="http://your-api-server:8000/static/js/chatbot-widget.js"
    data-api-url="http://your-api-server:8000"
    data-theme="light"
    data-position="bottom-right"
    data-primary-color="#007bff">
</script>
```

### Available Options

- `data-api-url`: API server URL (default: auto-detected from script src)
- `data-theme`: Widget theme - `light` or `dark` (default: `light`)
- `data-position`: Widget position - `bottom-right` or `bottom-left` (default: `bottom-right`)
- `data-primary-color`: Primary color in hex format (default: `#007bff`)

## CORS Configuration

Make sure your FastAPI server allows requests from your WordPress domain. Update `.env`:

```bash
CORS_ORIGINS=http://your-wordpress-site.com,https://your-wordpress-site.com
```

Then restart the FastAPI server.

## Testing

1. **Test API Health:**
   ```bash
   curl http://your-api-server:8000/api/health
   ```

2. **Test Chat Endpoint:**
   ```bash
   curl -X POST http://your-api-server:8000/api/chat \
     -H "Content-Type: application/json" \
     -d '{"question": "Hello", "session_id": "test123"}'
   ```

3. **Test Widget:**
   - Add script tags to a test WordPress page
   - Open the page in browser
   - Click the chat button
   - Send a test message

## Troubleshooting

### Widget doesn't appear

1. Check browser console for JavaScript errors
2. Verify script and CSS files are accessible
3. Check CORS configuration in `.env`
4. Ensure FastAPI server is running

### API calls fail

1. Check API server is running: `curl http://your-api-server:8000/api/health`
2. Verify CORS origins include your WordPress domain
3. Check browser network tab for error details
4. Verify `.env` file has correct `GROQ_API_KEY`

### Session not persisting

- Sessions are stored in browser `localStorage`
- Clear browser cache/localStorage if issues persist
- Check browser console for errors

## Customization

### Styling

You can override widget styles by adding custom CSS after the widget CSS:

```html
<link rel="stylesheet" href="http://your-api-server:8000/static/css/chatbot-widget.css">
<style>
    /* Your custom styles */
    .chatbot-toggle {
        background-color: #your-color !important;
    }
</style>
```

### JavaScript Events

The widget exposes a global `window.chatbotWidget` object:

```javascript
// Access widget instance
const widget = window.chatbotWidget;

// Manually open/close chat
widget.toggleChat();

// Send message programmatically
widget.sendMessage();
```

## Production Deployment

1. **Use HTTPS:** Update API URLs to use HTTPS
2. **CDN:** Host widget files on CDN for better performance
3. **Process Manager:** Use systemd/supervisor to keep API server running
4. **Reverse Proxy:** Use nginx as reverse proxy for API server
5. **Monitoring:** Set up logging and monitoring for API server

## Support

For issues or questions, check:
- API server logs
- Browser console
- FastAPI docs at `http://your-api-server:8000/docs`
