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
            this.lastQuestion = null;
            
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
            // Don't allow manual fullscreen toggle on mobile - it's always fullscreen
            if (this.isMobileDevice()) {
                return;
            }
            
            const chatWindow = document.getElementById('chatbot-window');
            const widget = document.getElementById('chatbot-widget');
            const fullscreenBtn = document.getElementById('chatbot-fullscreen');
            const header = chatWindow?.querySelector('.chatbot-header');
            const headerTitle = header?.querySelector('h3');
            const headerActions = header?.querySelector('.chatbot-header-actions');
            
            if (!this.isFullscreen) {
                // Enter fullscreen
                chatWindow.classList.add('chatbot-fullscreen');
                widget.classList.add('chatbot-fullscreen-active');
                chatWindow.style.display = 'flex'; // Ensure it's displayed
                this.isFullscreen = true;
                document.body.style.overflow = 'hidden';
                
                // Update button icon to minimize
                if (fullscreenBtn) {
                    fullscreenBtn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path>
                        </svg>
                    `;
                    fullscreenBtn.setAttribute('aria-label', 'Minimize');
                }
                
                // Force header visibility with inline styles
                if (header) {
                    header.style.display = 'flex';
                    header.style.visibility = 'visible';
                    header.style.opacity = '1';
                    header.style.position = 'relative';
                    header.style.zIndex = '10';
                    header.style.backgroundColor = 'var(--chatbot-bg-color)';
                    header.style.color = 'var(--chatbot-text-color)';
                    header.style.padding = '16px 24px';
                    header.style.borderBottom = '1px solid var(--chatbot-border-color)';
                }
                
                if (headerTitle) {
                    headerTitle.style.display = 'block';
                    headerTitle.style.visibility = 'visible';
                    headerTitle.style.opacity = '1';
                    headerTitle.style.color = 'var(--chatbot-text-color)';
                }
                
                if (headerActions) {
                    headerActions.style.display = 'flex';
                    headerActions.style.visibility = 'visible';
                    headerActions.style.opacity = '1';
                }
                
                // Ensure input container and textarea are visible
                const inputContainer = chatWindow.querySelector('.chatbot-input-container');
                const inputWrapper = chatWindow.querySelector('.chatbot-input-wrapper');
                const input = document.getElementById('chatbot-input');
                const sendBtn = document.getElementById('chatbot-send');
                const disclaimer = chatWindow.querySelector('.chatbot-disclaimer');
                
                if (inputContainer) {
                    inputContainer.style.display = 'block';
                    inputContainer.style.visibility = 'visible';
                    inputContainer.style.opacity = '1';
                }
                
                if (inputWrapper) {
                    inputWrapper.style.display = 'block';
                    inputWrapper.style.visibility = 'visible';
                    inputWrapper.style.opacity = '1';
                }
                
                if (input) {
                    input.style.display = 'block';
                    input.style.visibility = 'visible';
                    input.style.opacity = '1';
                }
                
                if (sendBtn) {
                    sendBtn.style.display = 'flex';
                    sendBtn.style.visibility = 'visible';
                    sendBtn.style.opacity = '1';
                }
                
                if (disclaimer) {
                    disclaimer.style.display = 'block';
                    disclaimer.style.visibility = 'visible';
                    disclaimer.style.opacity = '1';
                }
                
                // Update button icon to minimize (already done above)
            } else {
                // Exit fullscreen (minimize to small window)
                chatWindow.classList.remove('chatbot-fullscreen');
                widget.classList.remove('chatbot-fullscreen-active');
                this.isFullscreen = false;
                document.body.style.overflow = '';
                
                // Ensure header remains visible
                if (header) {
                    header.style.display = 'flex';
                    header.style.visibility = 'visible';
                    header.style.opacity = '1';
                }
                
                // Update icon back to fullscreen (expand)
                if (fullscreenBtn) {
                    fullscreenBtn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                        </svg>
                    `;
                    fullscreenBtn.setAttribute('aria-label', 'Fullscreen');
                }
            }
        }
        
        showWelcomeScreen() {
            const welcomeScreen = document.getElementById('chatbot-welcome');
            if (welcomeScreen) {
                welcomeScreen.style.display = 'flex';
            }
        }
        
        hideWelcomeScreen() {
            const welcomeScreen = document.getElementById('chatbot-welcome');
            if (welcomeScreen) {
                welcomeScreen.style.display = 'none';
            }
        }
        
        fillPromptFromCard(text, intent = null) {
            // Map card prompts to optimized queries that trigger specific intents
            const queryMap = {
                "Check availability & book a cottage": "I want to check availability and book a cottage for my dates",
                "View images of the cottages": "Show me images and photos of the cottages",
                "Prices & cottage options": "What are the prices and cottage options? Compare weekday and weekend rates",
                "Location & nearby attractions": "Tell me about the location and nearby attractions near Swiss Cottages Bhurban"
            };
            
            // Use optimized query if available, otherwise use original text
            const optimizedQuery = queryMap[text] || text;
            
            const input = document.getElementById('chatbot-input');
            if (input) {
                input.value = optimizedQuery;
                // Store intent in input data attribute for backend detection
                if (intent) {
                    input.setAttribute('data-intent', intent);
                }
                this.updateSendButton();
                input.focus();
                // Auto-resize textarea
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 200) + 'px';
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
                // Remove only message elements, preserve welcome screen
                const messageElements = messagesContainer.querySelectorAll('.chatbot-message, .chatbot-loading');
                messageElements.forEach(el => el.remove());
            }
            
            // Clear input
            const input = document.getElementById('chatbot-input');
            if (input) {
                input.value = '';
                input.style.height = 'auto';
                this.updateSendButton();
            }
            
            // Show welcome screen again
            this.showWelcomeScreen();
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
                        <div class="chatbot-header-left">
                            <div class="chatbot-logo">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                    <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline>
                                </svg>
                            </div>
                            <h3 class="chatbot-header-title">Swiss AI Assistant</h3>
                        </div>
                        <div class="chatbot-header-actions">
                            <button id="chatbot-fullscreen" class="chatbot-icon-btn chatbot-fullscreen-btn" aria-label="Fullscreen">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                                </svg>
                            </button>
                            <button id="chatbot-menu" class="chatbot-icon-btn chatbot-menu-btn" aria-label="More options">
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
                            <button id="chatbot-close" class="chatbot-icon-btn chatbot-close-btn" aria-label="Close chat">×</button>
                        </div>
                    </div>
                    <div id="chatbot-messages" class="chatbot-messages">
                        <div id="chatbot-welcome" class="chatbot-welcome">
                            <div class="chatbot-welcome-content">
                                <div class="chatbot-welcome-icon">
                                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                        <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline>
                                    </svg>
                                </div>
                                <h2 class="chatbot-welcome-title">How can I help you today?</h2>
                                <p class="chatbot-welcome-description">I'm here to assist you with finding and booking the perfect cottage or room for your stay.</p>
                                <div class="chatbot-suggestion-cards">
                                    <div class="chatbot-suggestion-card" data-prompt="Check availability & book a cottage" data-intent="booking">
                                        <div class="chatbot-card-content">
                                            <div class="chatbot-card-title">Check availability & book a cottage</div>
                                            <div class="chatbot-card-subtitle">Select your dates and guests to see available cottages</div>
                                        </div>
                                    </div>
                                    <div class="chatbot-suggestion-card" data-prompt="View images of the cottages" data-intent="images">
                                        <div class="chatbot-card-content">
                                            <div class="chatbot-card-title">View images of the cottages</div>
                                            <div class="chatbot-card-subtitle">See real photos of bedrooms, lounges, views, and outdoor areas</div>
                                        </div>
                                    </div>
                                    <div class="chatbot-suggestion-card" data-prompt="Prices & cottage options" data-intent="pricing">
                                        <div class="chatbot-card-content">
                                            <div class="chatbot-card-title">Prices & cottage options</div>
                                            <div class="chatbot-card-subtitle">Compare weekday and weekend prices for each cottage</div>
                                        </div>
                                    </div>
                                    <div class="chatbot-suggestion-card" data-prompt="Location & nearby attractions" data-intent="location">
                                        <div class="chatbot-card-content">
                                            <div class="chatbot-card-title">Location & nearby attractions</div>
                                            <div class="chatbot-card-subtitle">Find us near PC Bhurban and explore nearby spots</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="chatbot-input-container">
                        <div class="chatbot-input-wrapper">
                            <textarea 
                                id="chatbot-input" 
                                class="chatbot-input" 
                                placeholder="Message Swiss AI Assistant..."
                                rows="1"
                                autocomplete="off"
                            ></textarea>
                            <button id="chatbot-send" class="chatbot-send" aria-label="Send message" disabled>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <line x1="22" y1="2" x2="11" y2="13"></line>
                                    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                                </svg>
                            </button>
                        </div>
                        <div class="chatbot-disclaimer">
                            Swiss AI Assistant can make mistakes. Consider checking important information.
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(widget);
            
            // Show welcome screen initially
            this.showWelcomeScreen();
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
            
            // Suggestion card clicks
            const suggestionCards = document.querySelectorAll('.chatbot-suggestion-card');
            suggestionCards.forEach(card => {
                card.addEventListener('click', () => {
                    const prompt = card.getAttribute('data-prompt');
                    const intent = card.getAttribute('data-intent');
                    if (prompt) {
                        this.fillPromptFromCard(prompt, intent);
                        // Auto-send the message from card
                        setTimeout(() => {
                            this.sendMessage();
                        }, 100);
                    }
                });
            });
            
            // Textarea auto-resize and send button update
            if (input) {
                input.addEventListener('input', () => {
                    // Auto-resize
                    input.style.height = 'auto';
                    input.style.height = Math.min(input.scrollHeight, 200) + 'px';
                    // Update send button
                    this.updateSendButton();
                });
                
                // Send on Enter, new line on Shift+Enter
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (!send.disabled) {
                            this.sendMessage();
                        }
                    }
                });
            }
            
            // Initial send button state
            this.updateSendButton();
            
            // Fullscreen toggle
            if (fullscreenBtn) {
                fullscreenBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.toggleFullscreen();
                });
            }
            
            // Close fullscreen when clicking backdrop (using mousedown to catch ::before pseudo-element)
            const widget = document.getElementById('chatbot-widget');
            const chatWindow = document.getElementById('chatbot-window');
            if (widget && chatWindow) {
                // Use capture phase to catch backdrop clicks
                widget.addEventListener('click', (e) => {
                    if (this.isFullscreen && !this.isMobileDevice()) {
                        // Check if click is outside the window
                        const rect = chatWindow.getBoundingClientRect();
                        const clickX = e.clientX;
                        const clickY = e.clientY;
                        
                        if (clickX < rect.left || clickX > rect.right || 
                            clickY < rect.top || clickY > rect.bottom) {
                            // Clicked outside the window - close fullscreen
                            this.toggleFullscreen();
                        }
                    }
                }, true);
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
            
        }
        
        updateSendButton() {
            const input = document.getElementById('chatbot-input');
            const sendBtn = document.getElementById('chatbot-send');
            
            if (input && sendBtn) {
                if (input.value.trim()) {
                    sendBtn.disabled = false;
                    sendBtn.classList.remove('disabled');
                } else {
                    sendBtn.disabled = true;
                    sendBtn.classList.add('disabled');
                }
            }
        }
        
        isMobileDevice() {
            return window.innerWidth <= 768 || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        }
        
        toggleChat() {
            const chatWindow = document.getElementById('chatbot-window');
            const widget = document.getElementById('chatbot-widget');
            const toggleBtn = document.getElementById('chatbot-toggle');
            this.isOpen = !this.isOpen;
            
            if (this.isOpen) {
                chatWindow.style.display = 'flex';
                
                // Open in fullscreen by default (on desktop only)
                if (!this.isMobileDevice()) {
                    // Set fullscreen state
                    this.isFullscreen = true;
                    chatWindow.classList.add('chatbot-fullscreen');
                    widget.classList.add('chatbot-fullscreen-active');
                    document.body.style.overflow = 'hidden';
                    
                    // Update fullscreen button icon to minimize
                    const fullscreenBtn = document.getElementById('chatbot-fullscreen');
                    if (fullscreenBtn) {
                        fullscreenBtn.innerHTML = `
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path>
                            </svg>
                        `;
                        fullscreenBtn.setAttribute('aria-label', 'Minimize');
                    }
                    
                    // Ensure all fullscreen elements are visible
                    const header = chatWindow.querySelector('.chatbot-header');
                    if (header) {
                        header.style.display = 'flex';
                        header.style.visibility = 'visible';
                        header.style.opacity = '1';
                    }
                } else {
                    // Mobile - ensure header is visible
                    const header = chatWindow.querySelector('.chatbot-header');
                    if (header) {
                        header.style.display = 'flex';
                        header.style.visibility = 'visible';
                        header.style.opacity = '1';
                    }
                }
                
                // On mobile, ensure input and send button are visible and functional
                if (this.isMobileDevice()) {
                    const inputContainer = document.querySelector('.chatbot-input-container');
                    const input = document.getElementById('chatbot-input');
                    const sendBtn = document.getElementById('chatbot-send');
                    
                    if (inputContainer) {
                        inputContainer.style.display = 'flex';
                        inputContainer.style.visibility = 'visible';
                        inputContainer.style.opacity = '1';
                    }
                    
                    if (input) {
                        input.style.display = 'block';
                        input.style.visibility = 'visible';
                        input.style.opacity = '1';
                        // Small delay to ensure window is visible before focusing
                        setTimeout(() => {
                            input.focus();
                        }, 200);
                    }
                    
                    if (sendBtn) {
                        sendBtn.style.display = 'flex';
                        sendBtn.style.visibility = 'visible';
                        sendBtn.style.opacity = '1';
                    }
                } else {
                    // Desktop - focus input
                    setTimeout(() => {
                        const input = document.getElementById('chatbot-input');
                        if (input) {
                            input.focus();
                        }
                    }, 100);
                }
                
                // Clear backend session when opening chat to ensure fresh start
                this.clearBackendSession(this.sessionId);
            } else {
                chatWindow.style.display = 'none';
                widget.classList.remove('chatbot-open');
                
                // Reset fullscreen state when closing (desktop)
                if (!this.isMobileDevice()) {
                    chatWindow.classList.remove('chatbot-fullscreen');
                    widget.classList.remove('chatbot-fullscreen-active');
                    this.isFullscreen = false;
                    document.body.style.overflow = '';
                    
                    // Reset fullscreen button icon
                    const fullscreenBtn = document.getElementById('chatbot-fullscreen');
                    if (fullscreenBtn) {
                        fullscreenBtn.innerHTML = `
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                            </svg>
                        `;
                        fullscreenBtn.setAttribute('aria-label', 'Fullscreen');
                    }
                }
                
                // On mobile, remove fullscreen class when closing and restore site
                if (this.isMobileDevice()) {
                    chatWindow.classList.remove('chatbot-fullscreen');
                    this.isFullscreen = false;
                    
                    // Show toggle button again
                    if (toggleBtn) {
                        toggleBtn.style.display = 'flex';
                    }
                    
                    // Restore body scroll
                    document.body.classList.remove('chatbot-open-mobile');
                    document.body.style.overflow = '';
                    document.body.style.position = '';
                    document.body.style.width = '';
                    document.body.style.height = '';
                    
                    // Show all site content again
                    const siteElements = document.querySelectorAll('body > *:not(#chatbot-widget)');
                    siteElements.forEach(el => {
                        if (el.tagName !== 'SCRIPT' && el.tagName !== 'STYLE' && el.id !== 'chatbot-widget') {
                            el.style.display = '';
                            el.style.visibility = '';
                        }
                    });
                    
                    // Show WordPress elements again
                    const wpElements = document.querySelectorAll('header, footer, nav, .site-header, .main-header, #masthead, .navbar, .navigation, #main, .site-content, .content-area, main');
                    wpElements.forEach(el => {
                        if (!el.closest('#chatbot-widget')) {
                            el.style.display = '';
                            el.style.visibility = '';
                        }
                    });
                    
                    // Show WordPress admin bar again
                    const adminBar = document.getElementById('wpadminbar');
                    if (adminBar) {
                        adminBar.style.display = '';
                    }
                    
                    // Restore scroll position
                    if (this.scrollY !== undefined) {
                        window.scrollTo(0, this.scrollY);
                    }
                }
            }
        }
        
        addMessage(role, content, sources = null, images = null) {
            // Hide welcome screen when first user message is added
            if (role === 'user' && this.messages.length === 0) {
                this.hideWelcomeScreen();
            }
            
            const messagesContainer = document.getElementById('chatbot-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `chatbot-message chatbot-message-${role}`;
            
            let messageHTML = '';
            
            // Sources removed - not displaying retrieved sources anymore
            // if (sources && sources.length > 0) {
            //     messageHTML += '<div class="chatbot-sources"><strong>Retrieved sources:</strong><ol>';
            //     sources.forEach((source, index) => {
            //         const docName = source.document || 'Unknown source';
            //         const displayName = docName.split('/').pop().replace('.md', '') || docName;
            //         messageHTML += `<li>${displayName}`;
            //         if (source.score && source.score !== 'N/A') {
            //             messageHTML += ` <span class="chatbot-score">(score: ${source.score})</span>`;
            //         }
            //         messageHTML += `</li>`;
            //     });
            //     messageHTML += '</ol></div>';
            // }
            
            // Then add the answer content (like Streamlit)
            messageHTML += `<div class="chatbot-message-content">${this.formatMessage(content)}</div>`;
            
            // Add images if available - create horizontal gallery
            // Handle both array format (single cottage) and dict format (multiple cottages grouped)
            if (images) {
                // Check if images is a dictionary (grouped by cottage)
                if (images && typeof images === 'object' && !Array.isArray(images)) {
                    // Grouped by cottage - create separate gallery for each cottage
                    console.log('Creating grouped image galleries for cottages:', Object.keys(images));
                    
                    // Sort cottage numbers to display in order (7, 9, 11)
                    const cottageNumbers = Object.keys(images).sort((a, b) => {
                        const numA = parseInt(a);
                        const numB = parseInt(b);
                        return numA - numB;
                    });
                    
                    cottageNumbers.forEach((cottageNum) => {
                        const cottageImages = images[cottageNum];
                        if (cottageImages && Array.isArray(cottageImages) && cottageImages.length > 0) {
                            messageHTML += `<div class="chatbot-cottage-images-group">`;
                            messageHTML += `<h4 class="chatbot-cottage-title">Cottage ${cottageNum}</h4>`;
                            messageHTML += '<div class="chatbot-image-gallery">';
                            
                            cottageImages.forEach((imgUrl, index) => {
                                if (!imgUrl) {
                                    console.warn(`Image URL at index ${index} is empty for Cottage ${cottageNum}`);
                                    return;
                                }
                                
                                // Ensure URL is properly formatted
                                let fullUrl = imgUrl;
                                
                                // If it's already a full URL, use it as is
                                if (imgUrl.startsWith('http://') || imgUrl.startsWith('https://')) {
                                    fullUrl = imgUrl;
                                } 
                                // If it starts with /, it's a relative path from API base
                                else if (imgUrl.startsWith('/')) {
                                    const baseUrl = this.apiUrl.endsWith('/') ? this.apiUrl.slice(0, -1) : this.apiUrl;
                                    fullUrl = `${baseUrl}${imgUrl}`;
                                } 
                                // Otherwise, treat as relative and add to API base
                                else {
                                    const baseUrl = this.apiUrl.endsWith('/') ? this.apiUrl : `${this.apiUrl}/`;
                                    fullUrl = `${baseUrl}${imgUrl}`;
                                }
                                
                                messageHTML += `<img src="${fullUrl}" alt="Cottage ${cottageNum} image ${index + 1}" class="chatbot-cottage-image" loading="lazy" onerror="this.style.display='none';" />`;
                            });
                            
                            messageHTML += '</div>'; // chatbot-image-gallery
                            messageHTML += '</div>'; // chatbot-cottage-images-group
                        }
                    });
                } else if (Array.isArray(images) && images.length > 0) {
                    // Single array format (backward compatibility)
                    console.log('Creating image gallery with', images.length, 'images');
                    console.log('API URL:', this.apiUrl);
                    
                    messageHTML += '<div class="chatbot-image-gallery">';
                    images.forEach((imgUrl, index) => {
                        if (!imgUrl) {
                            console.warn(`Image URL at index ${index} is empty`);
                            return;
                        }
                        
                        // Ensure URL is properly formatted
                        let fullUrl = imgUrl;
                        
                        // If it's already a full URL, use it as is
                        if (imgUrl.startsWith('http://') || imgUrl.startsWith('https://')) {
                            fullUrl = imgUrl;
                        } 
                        // If it starts with /, it's a relative path from API base
                        else if (imgUrl.startsWith('/')) {
                            // Remove trailing slash from apiUrl if present, then add the image path
                            const baseUrl = this.apiUrl.endsWith('/') ? this.apiUrl.slice(0, -1) : this.apiUrl;
                            fullUrl = `${baseUrl}${imgUrl}`;
                        } 
                        // Otherwise, treat as relative and add to API base
                        else {
                            const baseUrl = this.apiUrl.endsWith('/') ? this.apiUrl : `${this.apiUrl}/`;
                            fullUrl = `${baseUrl}${imgUrl}`;
                        }
                        
                        console.log(`Image [${index}]: Original="${imgUrl}", Full="${fullUrl}"`);
                        
                        messageHTML += `<img src="${fullUrl}" alt="Cottage image ${index + 1}" class="chatbot-cottage-image" loading="lazy" onerror="this.style.display='none';" />`;
                    });
                    messageHTML += '</div>'; // chatbot-image-gallery
                }
            }
            
            messageDiv.innerHTML = messageHTML;
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            
            this.messages.push({ role, content });
        }
        
        initImageSlider(sliderId) {
            const slider = document.getElementById(sliderId);
            if (!slider) return;
            
            const slides = slider.querySelectorAll('.chatbot-slide');
            const dots = slider.querySelectorAll('.chatbot-slider-dot');
            const prevBtn = slider.querySelector('.chatbot-slider-prev');
            const nextBtn = slider.querySelector('.chatbot-slider-next');
            
            if (slides.length === 0) return;
            
            let currentSlide = 0;
            
            const showSlide = (index) => {
                // Handle wrap-around
                if (index >= slides.length) {
                    currentSlide = 0;
                } else if (index < 0) {
                    currentSlide = slides.length - 1;
                } else {
                    currentSlide = index;
                }
                
                // Update slides
                slides.forEach((slide, i) => {
                    slide.classList.toggle('active', i === currentSlide);
                });
                
                // Update dots
                dots.forEach((dot, i) => {
                    dot.classList.toggle('active', i === currentSlide);
                });
            };
            
            // Previous button
            if (prevBtn) {
                prevBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showSlide(currentSlide - 1);
                });
            }
            
            // Next button
            if (nextBtn) {
                nextBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showSlide(currentSlide + 1);
                });
            }
            
            // Dot navigation
            dots.forEach((dot, index) => {
                dot.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showSlide(index);
                });
            });
            
            // Keyboard navigation
            slider.setAttribute('tabindex', '0'); // Make slider focusable
            slider.addEventListener('keydown', (e) => {
                if (e.key === 'ArrowLeft') {
                    e.preventDefault();
                    showSlide(currentSlide - 1);
                } else if (e.key === 'ArrowRight') {
                    e.preventDefault();
                    showSlide(currentSlide + 1);
                }
            });
            
            // Touch/swipe support for mobile
            let touchStartX = 0;
            let touchEndX = 0;
            
            slider.addEventListener('touchstart', (e) => {
                touchStartX = e.changedTouches[0].screenX;
            }, { passive: true });
            
            slider.addEventListener('touchend', (e) => {
                touchEndX = e.changedTouches[0].screenX;
                handleSwipe();
            }, { passive: true });
            
            const handleSwipe = () => {
                const swipeThreshold = 50; // Minimum swipe distance
                const diff = touchStartX - touchEndX;
                
                if (Math.abs(diff) > swipeThreshold) {
                    if (diff > 0) {
                        // Swipe left - next image
                        showSlide(currentSlide + 1);
                    } else {
                        // Swipe right - previous image
                        showSlide(currentSlide - 1);
                    }
                }
            };
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
        
        renderFollowUpActions(messageDiv, followUpActions) {
            if (!followUpActions) return;
            
            // Create actions container
            const actionsContainer = document.createElement('div');
            actionsContainer.className = 'chatbot-follow-up-actions';
            
            // Add quick action buttons
            if (followUpActions.quick_actions && followUpActions.quick_actions.length > 0) {
                const quickActionsDiv = document.createElement('div');
                quickActionsDiv.className = 'chatbot-quick-actions';
                
                followUpActions.quick_actions.forEach(action => {
                    const button = document.createElement('button');
                    button.className = 'chatbot-quick-action-btn';
                    button.textContent = action.text;
                    button.setAttribute('data-action', action.action);
                    button.setAttribute('type', 'button');
                    
                    // Handle button click
                    button.addEventListener('click', () => {
                        this.handleQuickAction(action);
                    });
                    
                    quickActionsDiv.appendChild(button);
                });
                
                actionsContainer.appendChild(quickActionsDiv);
            }
            
            // Add suggestion chips
            if (followUpActions.suggestions && followUpActions.suggestions.length > 0) {
                const suggestionsDiv = document.createElement('div');
                suggestionsDiv.className = 'chatbot-suggestions';
                
                followUpActions.suggestions.forEach(suggestion => {
                    const chip = document.createElement('button');
                    chip.className = 'chatbot-suggestion-chip';
                    chip.textContent = suggestion;
                    chip.setAttribute('type', 'button');
                    
                    // Handle chip click
                    chip.addEventListener('click', () => {
                        this.fillPromptFromCard(suggestion);
                        setTimeout(() => {
                            this.sendMessage();
                        }, 100);
                    });
                    
                    suggestionsDiv.appendChild(chip);
                });
                
                actionsContainer.appendChild(suggestionsDiv);
            }
            
            // Append to message div
            if (actionsContainer.children.length > 0) {
                messageDiv.appendChild(actionsContainer);
            }
        }
        
        handleQuickAction(action) {
            const actionMap = {
                'booking': 'I want to check availability and book a cottage',
                'contact': 'How can I contact the manager?',
                'pricing': 'What are the prices and cottage options?',
                'availability': 'Check availability for my dates',
                'images': 'Show me images of the cottages'
            };
            
            const query = actionMap[action.action] || action.text;
            this.fillPromptFromCard(query);
            setTimeout(() => {
                this.sendMessage();
            }, 100);
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
        
        showSearching(message = 'Searching...') {
            const messagesContainer = document.getElementById('chatbot-messages');
            let searchingDiv = document.getElementById('chatbot-searching');
            
            if (!searchingDiv) {
                searchingDiv = document.createElement('div');
                searchingDiv.id = 'chatbot-searching';
                searchingDiv.className = 'chatbot-message chatbot-message-assistant chatbot-searching';
                searchingDiv.innerHTML = `
                    <div class="chatbot-message-content">
                        <span class="chatbot-searching-text">${message}</span>
                        <span class="chatbot-searching-dots">
                            <span class="dot"></span>
                            <span class="dot"></span>
                            <span class="dot"></span>
                        </span>
                    </div>
                `;
                messagesContainer.appendChild(searchingDiv);
            } else {
                const textSpan = searchingDiv.querySelector('.chatbot-searching-text');
                if (textSpan) {
                    textSpan.textContent = message;
                }
                searchingDiv.style.display = 'flex';
            }
            
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        hideSearching() {
            const searchingDiv = document.getElementById('chatbot-searching');
            if (searchingDiv) {
                searchingDiv.remove();
            }
        }
        
        createSourcesDiv(sources) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'chatbot-sources';
            let html = '<strong>Retrieved sources:</strong><ol>';
            sources.forEach((source) => {
                const docName = source.document || source.document || 'Unknown source';
                const displayName = docName.split('/').pop().replace('.md', '') || docName;
                html += `<li>${displayName}`;
                if (source.score && source.score !== 'N/A') {
                    html += ` <span class="chatbot-score">(score: ${source.score})</span>`;
                }
                html += `</li>`;
            });
            html += '</ol>';
            sourcesDiv.innerHTML = html;
            return sourcesDiv;
        }
        
        addImagesToMessage(messageDiv, images) {
            if (!images) return;
            
            // Handle grouped images (dict format) - multiple cottages
            if (images && typeof images === 'object' && !Array.isArray(images)) {
                // Grouped by cottage - create separate gallery for each cottage
                console.log('Adding grouped image galleries for cottages:', Object.keys(images));
                
                // Sort cottage numbers to display in order (7, 9, 11)
                const cottageNumbers = Object.keys(images).sort((a, b) => {
                    const numA = parseInt(a);
                    const numB = parseInt(b);
                    return numA - numB;
                });
                
                let groupedHTML = '';
                cottageNumbers.forEach((cottageNum) => {
                    const cottageImages = images[cottageNum];
                    if (cottageImages && Array.isArray(cottageImages) && cottageImages.length > 0) {
                        groupedHTML += `<div class="chatbot-cottage-images-group">`;
                        groupedHTML += `<h4 class="chatbot-cottage-title">Cottage ${cottageNum}</h4>`;
                        groupedHTML += '<div class="chatbot-image-gallery">';
                        
                        cottageImages.forEach((imgUrl, index) => {
                            if (!imgUrl) {
                                console.warn(`Image URL at index ${index} is empty for Cottage ${cottageNum}`);
                                return;
                            }
                            
                            // Ensure URL is properly formatted
                            let fullUrl = imgUrl;
                            
                            // If it's already a full URL, use it as is
                            if (imgUrl.startsWith('http://') || imgUrl.startsWith('https://')) {
                                fullUrl = imgUrl;
                            } 
                            // If it starts with /, it's a relative path from API base
                            else if (imgUrl.startsWith('/')) {
                                const baseUrl = this.apiUrl.endsWith('/') ? this.apiUrl.slice(0, -1) : this.apiUrl;
                                fullUrl = `${baseUrl}${imgUrl}`;
                            } 
                            // Otherwise, treat as relative and add to API base
                            else {
                                const baseUrl = this.apiUrl.endsWith('/') ? this.apiUrl : `${this.apiUrl}/`;
                                fullUrl = `${baseUrl}${imgUrl}`;
                            }
                            
                            groupedHTML += `<img src="${fullUrl}" alt="Cottage ${cottageNum} image ${index + 1}" class="chatbot-cottage-image" loading="lazy" onerror="this.style.display='none';" />`;
                        });
                        
                        groupedHTML += '</div>'; // chatbot-image-gallery
                        groupedHTML += '</div>'; // chatbot-cottage-images-group
                    }
                });
                
                messageDiv.insertAdjacentHTML('beforeend', groupedHTML);
                return;
            }
            
            // Handle single array format (backward compatibility)
            if (!Array.isArray(images) || images.length === 0) return;
            
            let galleryHTML = '<div class="chatbot-image-gallery">';
            images.forEach((imgUrl, index) => {
                if (!imgUrl) return;
                
                let fullUrl = imgUrl;
                if (imgUrl.startsWith('http://') || imgUrl.startsWith('https://')) {
                    fullUrl = imgUrl;
                } else if (imgUrl.startsWith('/')) {
                    const baseUrl = this.apiUrl.endsWith('/') ? this.apiUrl.slice(0, -1) : this.apiUrl;
                    fullUrl = `${baseUrl}${imgUrl}`;
                } else {
                    const baseUrl = this.apiUrl.endsWith('/') ? this.apiUrl : `${this.apiUrl}/`;
                    fullUrl = `${baseUrl}${imgUrl}`;
                }
                
                galleryHTML += `<img src="${fullUrl}" alt="Cottage image ${index + 1}" class="chatbot-cottage-image" loading="lazy" onerror="this.style.display='none';" />`;
            });
            galleryHTML += '</div>';
            
            messageDiv.insertAdjacentHTML('beforeend', galleryHTML);
        }
        
        async sendMessage(questionOverride = null) {
            const input = document.getElementById('chatbot-input');
            const question = questionOverride || input.value.trim();
            
            if (!question || this.isLoading) {
                return;
            }
            
            // Clear input and reset height
            input.value = '';
            input.style.height = 'auto';
            this.updateSendButton();
            
            // Add user message
            this.addMessage('user', question);
            
            // Create assistant message container for streaming
            const messagesContainer = document.getElementById('chatbot-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'chatbot-message chatbot-message-assistant chatbot-streaming';
            
            // Show thinking indicator immediately
            const thinkingIndicator = document.createElement('div');
            thinkingIndicator.className = 'chatbot-thinking-indicator';
            thinkingIndicator.innerHTML = '<span class="chatbot-thinking-dots"><span></span><span></span><span></span></span><span class="chatbot-thinking-text">Thinking...</span>';
            messageDiv.appendChild(thinkingIndicator);
            
            // Create content div (hidden initially)
            const contentDiv = document.createElement('div');
            contentDiv.className = 'chatbot-message-content';
            contentDiv.style.display = 'none';
            messageDiv.appendChild(contentDiv);
            
            messagesContainer.appendChild(messageDiv);
            let fullAnswer = '';
            let sources = null; // Keep for reference but don't display
            let images = null;
            let progressBar = null;
            let typingIndicator = null;
            let lastScrollTime = 0;
            
            try {
                // Use streaming endpoint
                const response = await fetch(`${this.apiUrl}/api/chat/stream`, {
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
                
                // Hide searching indicator
                this.hideSearching();
                
                // Read stream
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // Keep incomplete line in buffer
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                
                                if (data.type === 'searching') {
                                    // Update searching message
                                    this.showSearching(data.message || 'Searching...');
                                }
                                else if (data.type === 'hide_searching') {
                                    // Hide searching message (when fallback is shown)
                                    this.hideSearching();
                                }
                                else if (data.type === 'sources_found') {
                                    // Hide searching - sources are no longer displayed
                                    this.hideSearching();
                                    sources = data.sources; // Store for reference but don't display
                                    // Sources display removed - not showing retrieved sources anymore
                                }
                                else if (data.type === 'typing') {
                                    // Remove thinking indicator when typing starts
                                    const thinkingIndicator = messageDiv.querySelector('.chatbot-thinking-indicator');
                                    if (thinkingIndicator) {
                                        thinkingIndicator.remove();
                                        contentDiv.style.display = 'block';
                                    }
                                    
                                    // Show typing indicator
                                    if (!typingIndicator) {
                                        typingIndicator = document.createElement('div');
                                        typingIndicator.className = 'chatbot-typing-indicator';
                                        typingIndicator.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
                                        messageDiv.insertBefore(typingIndicator, contentDiv);
                                    }
                                }
                                else if (data.type === 'token') {
                                    // Remove thinking indicator when first token arrives
                                    const thinkingIndicator = messageDiv.querySelector('.chatbot-thinking-indicator');
                                    if (thinkingIndicator) {
                                        thinkingIndicator.remove();
                                        contentDiv.style.display = 'block';
                                    }
                                    
                                    // Remove typing indicator when first token arrives
                                    if (typingIndicator) {
                                        typingIndicator.remove();
                                        typingIndicator = null;
                                    }
                                    
                                    // Sources are no longer displayed - removed
                                    
                                    // Append token to answer
                                    fullAnswer += data.chunk;
                                    contentDiv.innerHTML = this.formatMessage(fullAnswer) + '<span class="chatbot-cursor">▌</span>';
                                    
                                    // Smooth auto-scroll (throttled)
                                    const now = Date.now();
                                    if (now - lastScrollTime > 50) { // Scroll every 50ms max
                                        messagesContainer.scrollTop = messagesContainer.scrollHeight;
                                        lastScrollTime = now;
                                    }
                                }
                                else if (data.type === 'progress') {
                                    // Update progress bar
                                    if (!progressBar) {
                                        progressBar = document.createElement('div');
                                        progressBar.className = 'chatbot-progress-bar';
                                        progressBar.innerHTML = '<div class="chatbot-progress-fill"></div>';
                                        messageDiv.insertBefore(progressBar, contentDiv);
                                    }
                                    const progressFill = progressBar.querySelector('.chatbot-progress-fill');
                                    if (progressFill) {
                                        progressFill.style.width = `${data.progress}%`;
                                    }
                                }
                                else if (data.type === 'done') {
                                    // Remove thinking indicator if still showing
                                    const thinkingIndicator = messageDiv.querySelector('.chatbot-thinking-indicator');
                                    if (thinkingIndicator) {
                                        thinkingIndicator.remove();
                                        contentDiv.style.display = 'block';
                                    }
                                    
                                    // Remove cursor and typing indicator
                                    if (typingIndicator) {
                                        typingIndicator.remove();
                                    }
                                    contentDiv.innerHTML = this.formatMessage(fullAnswer);
                                    
                                    // Hide progress bar
                                    if (progressBar) {
                                        progressBar.remove();
                                    }
                                    
                                    // Sources are no longer displayed - removed
                                    // if (data.sources && !sources) {
                                    //     sources = data.sources;
                                    //     if (sources && sources.length > 0) {
                                    //         sourcesDiv = this.createSourcesDiv(sources);
                                    //         messageDiv.insertBefore(sourcesDiv, contentDiv);
                                    //     }
                                    // }
                                    
                                    // Add images if available
                                    if (data.cottage_images) {
                                        images = data.cottage_images;
                                        this.addImagesToMessage(messageDiv, images);
                                    }
                                    
                                    // Add follow-up actions if available
                                    if (data.follow_up_actions) {
                                        this.renderFollowUpActions(messageDiv, data.follow_up_actions);
                                    }
                                    
                                    messageDiv.classList.remove('chatbot-streaming');
                                    this.messages.push({ role: 'assistant', content: fullAnswer });
                                    
                                    // Final scroll
                                    messagesContainer.scrollTop = messagesContainer.scrollHeight;
                                }
                                else if (data.type === 'error') {
                                    throw new Error(data.message);
                                }
                            } catch (e) {
                                console.error('Error parsing SSE data:', e, line);
                            }
                        }
                    }
                }
                
            } catch (error) {
                console.error('Error sending message:', error);
                this.hideSearching();
                
                // Remove any indicators
                const thinkingIndicator = messageDiv.querySelector('.chatbot-thinking-indicator');
                if (thinkingIndicator) thinkingIndicator.remove();
                if (typingIndicator) typingIndicator.remove();
                if (progressBar) progressBar.remove();
                
                // Show error with retry button
                const errorMsg = 'Sorry, I encountered an error. Please try again.';
                contentDiv.style.display = 'block';
                contentDiv.innerHTML = this.formatMessage(errorMsg);
                messageDiv.classList.remove('chatbot-streaming');
                
                // Store question for retry
                this.lastQuestion = question;
                
                // Add retry button
                const retryBtn = document.createElement('button');
                retryBtn.className = 'chatbot-retry-btn';
                retryBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path><path d="M21 3v5h-5"></path><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path><path d="M3 21v-5h5"></path></svg> Retry';
                retryBtn.onclick = () => {
                    messageDiv.remove();
                    if (this.lastQuestion) {
                        const input = document.getElementById('chatbot-input');
                        input.value = this.lastQuestion;
                        this.updateSendButton();
                        this.sendMessage();
                    }
                };
                messageDiv.appendChild(retryBtn);
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
