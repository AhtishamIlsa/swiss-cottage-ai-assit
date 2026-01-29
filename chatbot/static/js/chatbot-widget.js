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
                
                // Update icon to restore
                if (fullscreenBtn) {
                    fullscreenBtn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path>
                        </svg>
                    `;
                    fullscreenBtn.style.display = 'flex';
                    fullscreenBtn.style.visibility = 'visible';
                    fullscreenBtn.style.opacity = '1';
                }
            } else {
                // Exit fullscreen
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
                
                // Update icon to fullscreen
                if (fullscreenBtn) {
                    fullscreenBtn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path>
                        </svg>
                    `;
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
        
        fillPromptFromCard(text) {
            const input = document.getElementById('chatbot-input');
            if (input) {
                input.value = text;
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
                            <h3 class="chatbot-header-title">Swiss Cottages Assistant</h3>
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
                                    <div class="chatbot-suggestion-card" data-prompt="Check availability & book a cottage">
                                        <div class="chatbot-card-content">
                                            <div class="chatbot-card-title">Check availability & book a cottage</div>
                                            <div class="chatbot-card-subtitle">Select your dates and guests to see available cottages</div>
                                        </div>
                                    </div>
                                    <div class="chatbot-suggestion-card" data-prompt="View images of the cottages">
                                        <div class="chatbot-card-content">
                                            <div class="chatbot-card-title">View images of the cottages</div>
                                            <div class="chatbot-card-subtitle">See real photos of bedrooms, lounges, views, and outdoor areas</div>
                                        </div>
                                    </div>
                                    <div class="chatbot-suggestion-card" data-prompt="Prices & cottage options">
                                        <div class="chatbot-card-content">
                                            <div class="chatbot-card-title">Prices & cottage options</div>
                                            <div class="chatbot-card-subtitle">Compare weekday and weekend prices for each cottage</div>
                                        </div>
                                    </div>
                                    <div class="chatbot-suggestion-card" data-prompt="Location & nearby attractions">
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
                                placeholder="Message Swiss Cottages Assistant..."
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
                            Swiss Cottages Assistant can make mistakes. Consider checking important information.
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
                    if (prompt) {
                        this.fillPromptFromCard(prompt);
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
                
                // Ensure header is visible
                const header = chatWindow.querySelector('.chatbot-header');
                if (header) {
                    header.style.display = 'flex';
                    header.style.visibility = 'visible';
                    header.style.opacity = '1';
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
            
            // Add images if available - create slider
            if (images && Array.isArray(images) && images.length > 0) {
                console.log('Creating image slider with', images.length, 'images');
                console.log('API URL:', this.apiUrl);
                
                const sliderId = `chatbot-slider-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
                messageHTML += `<div class="chatbot-image-slider" id="${sliderId}">`;
                messageHTML += '<div class="chatbot-slider-container">';
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
                    
                    messageHTML += `<div class="chatbot-slide ${index === 0 ? 'active' : ''}">`;
                    messageHTML += `<img src="${fullUrl}" alt="Cottage image ${index + 1}" class="chatbot-slider-image" onload="console.log('✅ Image loaded successfully:', '${fullUrl}'); this.style.opacity='1';" onerror="console.error('❌ Failed to load image:', '${fullUrl}', 'Status:', this.naturalWidth, 'x', this.naturalHeight); const parent = this.closest('.chatbot-slide'); if (parent) { parent.innerHTML='<div style=\\'display:flex;align-items:center;justify-content:center;height:100%;color:#999;\\'>Image not available</div>'; }" loading="lazy" style="opacity:0;transition:opacity 0.3s;" />`;
                    messageHTML += '</div>';
                });
                messageHTML += '</div>'; // slider-container
                
                // Navigation controls
                if (images.length > 1) {
                    messageHTML += '<button class="chatbot-slider-prev" aria-label="Previous image">‹</button>';
                    messageHTML += '<button class="chatbot-slider-next" aria-label="Next image">›</button>';
                    messageHTML += '<div class="chatbot-slider-dots">';
                    images.forEach((_, index) => {
                        messageHTML += `<span class="chatbot-slider-dot ${index === 0 ? 'active' : ''}" data-slide="${index}" aria-label="Go to image ${index + 1}"></span>`;
                    });
                    messageHTML += '</div>'; // slider-dots
                }
                
                messageHTML += '</div>'; // chatbot-image-slider
            }
            
            messageDiv.innerHTML = messageHTML;
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            
            // Initialize slider if images were added
            if (images && images.length > 0) {
                const slider = messageDiv.querySelector('.chatbot-image-slider');
                if (slider && slider.id) {
                    // Use setTimeout to ensure DOM is ready
                    setTimeout(() => {
                        this.initImageSlider(slider.id);
                    }, 100);
                }
            }
            
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
            
            // Clear input and reset height
            input.value = '';
            input.style.height = 'auto';
            this.updateSendButton();
            
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
                
                // Debug: Log the response to see what we're getting
                console.log('API Response:', data);
                console.log('Cottage images:', data.cottage_images);
                
                // Hide loading
                this.hideLoading();
                
                // Add assistant response
                this.addMessage(
                    'assistant',
                    data.answer,
                    data.sources,
                    data.cottage_images || null
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
