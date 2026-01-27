/**
 * Swiss Cottages Chatbot Widget
 * Auto-initializes when script loads
 */

(function() {
    'use strict';

    class ChatbotWidget {
        constructor(config = {}) {
            // Configuration
            this.apiUrl = config.apiUrl || this.getApiUrlFromScript() || 'http://localhost:8000';
            this.sessionId = this.getOrCreateSessionId();
            this.theme = config.theme || 'light';
            this.position = config.position || 'bottom-right';
            this.primaryColor = config.primaryColor || '#007bff';
            
            // State
            this.isOpen = false;
            this.isFullscreen = false;
            this.isLoading = false;
            this.messages = [];
            
            // Initialize
            this.initUI();
            this.bindEvents();
        }
        
        getApiUrlFromScript() {
            // Try to get API URL from script tag data attribute
            const scripts = document.getElementsByTagName('script');
            for (let script of scripts) {
                if (script.src && script.src.includes('chatbot-widget.js')) {
                    // Extract base URL from script src
                    const url = new URL(script.src);
                    return `${url.protocol}//${url.host}`;
                }
                if (script.dataset && script.dataset.apiUrl) {
                    return script.dataset.apiUrl;
                }
            }
            return null;
        }
        
        getOrCreateSessionId() {
            // Generate a new session ID on each page load (don't persist)
            // This ensures fresh chat history on every page refresh
            const sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            
            // Clear any old session from backend when creating new session
            // This ensures backend doesn't have stale history
            this.clearBackendSession(sessionId);
            
            return sessionId;
        }
        
        async clearBackendSession(sessionId) {
            // Clear backend session to ensure fresh start
            // Use a dummy old session ID to clear any potential old sessions
            try {
                // Try to clear any existing session (ignore errors if session doesn't exist)
                await fetch(`${this.options.apiUrl}/api/chat/clear`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ session_id: sessionId }),
                }).catch(() => {
                    // Ignore errors - session might not exist, which is fine
                });
            } catch (error) {
                // Ignore errors - this is just cleanup
            }
        }
        
        toggleFullscreen() {
            const window = document.getElementById('chatbot-window');
            const fullscreenBtn = document.getElementById('chatbot-fullscreen');
            
            if (!this.isFullscreen) {
                // Enter fullscreen
                window.classList.add('chatbot-fullscreen');
                this.isFullscreen = true;
                // Update icon to restore
                fullscreenBtn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path>
                    </svg>
                `;
            } else {
                // Exit fullscreen
                window.classList.remove('chatbot-fullscreen');
                this.isFullscreen = false;
                // Update icon to fullscreen
                fullscreenBtn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                    </svg>
                `;
            }
        }
        
        async restartConversation() {
            // Clear backend session
            await this.clearBackendSession(this.sessionId);
            
            // Generate new session ID
            this.sessionId = this.getOrCreateSessionId();
            
            // Clear frontend messages
            this.messages = [];
            const messagesContainer = document.getElementById('chatbot-messages');
            if (messagesContainer) {
                messagesContainer.innerHTML = '';
                // Add welcome message again
                this.addMessage('assistant', 'Hi! 👋 How may I help you today?\n\nI can help you with information about Swiss Cottages Bhurban, including:\n- Pricing and availability\n- Facilities and amenities\n- Location and nearby attractions\n- Booking and payment information\n\nWhat would you like to know?');
            }
        }
        
        initUI() {
            // Create widget container
            const widget = document.createElement('div');
            widget.id = 'chatbot-widget';
            widget.className = `chatbot-widget chatbot-${this.position}`;
            widget.innerHTML = `
                <button id="chatbot-toggle" class="chatbot-toggle" aria-label="Open chat">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                </button>
                <div id="chatbot-window" class="chatbot-window" style="display: none;">
                    <div class="chatbot-header">
                        <h3>Swiss Cottages Assistant</h3>
                        <div class="chatbot-header-actions">
                            <button id="chatbot-fullscreen" class="chatbot-icon-btn" aria-label="Fullscreen">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                                </svg>
                            </button>
                            <button id="chatbot-menu" class="chatbot-icon-btn" aria-label="More options">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="1"></circle>
                                    <circle cx="12" cy="5" r="1"></circle>
                                    <circle cx="12" cy="19" r="1"></circle>
                                </svg>
                            </button>
                            <div id="chatbot-menu-dropdown" class="chatbot-menu-dropdown" style="display: none;">
                                <button id="chatbot-restart" class="chatbot-menu-item">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path>
                                        <path d="M21 3v5h-5"></path>
                                        <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path>
                                        <path d="M3 21v-5h5"></path>
                                    </svg>
                                    <span>Restart Conversation</span>
                                </button>
                            </div>
                            <button id="chatbot-close" class="chatbot-icon-btn" aria-label="Close chat">×</button>
                        </div>
                    </div>
                    <div id="chatbot-messages" class="chatbot-messages"></div>
                    <div class="chatbot-input-container">
                        <input 
                            type="text" 
                            id="chatbot-input" 
                            class="chatbot-input" 
                            placeholder="Ask a question..."
                            autocomplete="off"
                        />
                        <button id="chatbot-send" class="chatbot-send" aria-label="Send message">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="22" y1="2" x2="11" y2="13"></line>
                                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(widget);
            
            // Add welcome message
            this.addMessage('assistant', 'Hi! 👋 How may I help you today?\n\nI can help you with information about Swiss Cottages Bhurban, including:\n- Pricing and availability\n- Facilities and amenities\n- Location and nearby attractions\n- Booking and payment information\n\nWhat would you like to know?');
        }
        
        bindEvents() {
            const toggle = document.getElementById('chatbot-toggle');
            const close = document.getElementById('chatbot-close');
            const send = document.getElementById('chatbot-send');
            const input = document.getElementById('chatbot-input');
            const menuBtn = document.getElementById('chatbot-menu');
            const menuDropdown = document.getElementById('chatbot-menu-dropdown');
            const restartBtn = document.getElementById('chatbot-restart');
            const fullscreenBtn = document.getElementById('chatbot-fullscreen');
            
            toggle.addEventListener('click', () => this.toggleChat());
            close.addEventListener('click', () => this.toggleChat());
            send.addEventListener('click', () => this.sendMessage());
            
            // Fullscreen toggle
            if (fullscreenBtn) {
                fullscreenBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.toggleFullscreen();
                });
            }
            
            // Menu toggle
            if (menuBtn && menuDropdown) {
                menuBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const isVisible = menuDropdown.style.display === 'block';
                    menuDropdown.style.display = isVisible ? 'none' : 'block';
                });
                
                // Close menu when clicking outside
                document.addEventListener('click', (e) => {
                    if (menuBtn && menuDropdown && 
                        !menuBtn.contains(e.target) && 
                        !menuDropdown.contains(e.target)) {
                        menuDropdown.style.display = 'none';
                    }
                });
                
                // Restart conversation
                if (restartBtn) {
                    restartBtn.addEventListener('click', () => {
                        this.restartConversation();
                        menuDropdown.style.display = 'none';
                    });
                }
            }
            
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        
        toggleChat() {
            const window = document.getElementById('chatbot-window');
            this.isOpen = !this.isOpen;
            
            if (this.isOpen) {
                window.style.display = 'flex';
                document.getElementById('chatbot-input').focus();
                // Clear backend session when opening chat to ensure fresh start
                this.clearBackendSession(this.sessionId);
            } else {
                window.style.display = 'none';
            }
        }
        
        addMessage(role, content, sources = null, images = null) {
            const messagesContainer = document.getElementById('chatbot-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `chatbot-message chatbot-message-${role}`;
            
            let messageHTML = '';
            
            // Add sources FIRST (like Streamlit) if available
            if (sources && sources.length > 0) {
                messageHTML += '<div class="chatbot-sources"><strong>Retrieved sources:</strong><ol>';
                sources.forEach((source, index) => {
                    const docName = source.document || 'Unknown source';
                    // Extract just the filename if it's a full path
                    const displayName = docName.split('/').pop().replace('.md', '') || docName;
                    messageHTML += `<li>${displayName}`;
                    if (source.score && source.score !== 'N/A') {
                        messageHTML += ` <span class="chatbot-score">(score: ${source.score})</span>`;
                    }
                    messageHTML += `</li>`;
                });
                messageHTML += '</ol></div>';
            }
            
            // Then add the answer content (like Streamlit)
            messageHTML += `<div class="chatbot-message-content">${this.formatMessage(content)}</div>`;
            
            // Add images if available
            if (images && images.length > 0) {
                messageHTML += '<div class="chatbot-images">';
                images.forEach(imgUrl => {
                    // Ensure URL is properly formatted
                    const fullUrl = imgUrl.startsWith('http') ? imgUrl : `${this.apiUrl}${imgUrl}`;
                    messageHTML += `<img src="${fullUrl}" alt="Cottage image" class="chatbot-image" onerror="this.style.display='none'; console.error('Failed to load image:', '${fullUrl}');" />`;
                });
                messageHTML += '</div>';
            }
            
            messageDiv.innerHTML = messageHTML;
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            
            this.messages.push({ role, content });
        }
        
        formatMessage(text) {
            // Simple markdown-like formatting
            return text
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*(.*?)\*/g, '<em>$1</em>')
                .replace(/\n/g, '<br>')
                .replace(/💡/g, '💡')
                .replace(/❌/g, '❌')
                .replace(/👋/g, '👋')
                .replace(/🏡/g, '🏡');
        }
        
        showLoading() {
            const messagesContainer = document.getElementById('chatbot-messages');
            const loadingDiv = document.createElement('div');
            loadingDiv.id = 'chatbot-loading';
            loadingDiv.className = 'chatbot-message chatbot-message-assistant chatbot-loading';
            loadingDiv.innerHTML = '<div class="chatbot-message-content">Thinking...</div>';
            messagesContainer.appendChild(loadingDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            this.isLoading = true;
        }
        
        hideLoading() {
            const loading = document.getElementById('chatbot-loading');
            if (loading) {
                loading.remove();
            }
            this.isLoading = false;
        }
        
        async sendMessage() {
            const input = document.getElementById('chatbot-input');
            const question = input.value.trim();
            
            if (!question || this.isLoading) {
                return;
            }
            
            // Clear input
            input.value = '';
            
            // Add user message
            this.addMessage('user', question);
            
            // Show loading
            this.showLoading();
            
            try {
                const response = await fetch(`${this.apiUrl}/api/chat`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        question: question,
                        session_id: this.sessionId,
                    }),
                });
                
                if (!response.ok) {
                    const errorText = await response.text();
                    let errorDetail = `HTTP error! status: ${response.status}`;
                    try {
                        const errorJson = JSON.parse(errorText);
                        if (errorJson.detail) {
                            errorDetail = errorJson.detail;
                        }
                    } catch (e) {
                        errorDetail = errorText || errorDetail;
                    }
                    throw new Error(errorDetail);
                }
                
                const data = await response.json();
                
                // Hide loading
                this.hideLoading();
                
                // Add assistant response
                this.addMessage(
                    'assistant',
                    data.answer,
                    data.sources,
                    data.cottage_images
                );
                
            } catch (error) {
                console.error('Error sending message:', error);
                this.hideLoading();
                
                // Show more detailed error message
                let errorMsg = 'Sorry, I encountered an error. Please try again later.';
                if (error.message) {
                    errorMsg += `\n\nError: ${error.message}`;
                }
                this.addMessage('assistant', errorMsg);
            }
        }
    }
    
    // Auto-initialize when DOM is ready
    function initWidget() {
        // Get configuration from script tag or data attributes
        const script = document.currentScript || 
                     document.querySelector('script[src*="chatbot-widget.js"]');
        
        const config = {
            apiUrl: script?.dataset?.apiUrl || null,
            theme: script?.dataset?.theme || 'light',
            position: script?.dataset?.position || 'bottom-right',
            primaryColor: script?.dataset?.primaryColor || '#007bff',
        };
        
        // Initialize widget
        window.chatbotWidget = new ChatbotWidget(config);
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initWidget);
    } else {
        initWidget();
    }
    
})();
