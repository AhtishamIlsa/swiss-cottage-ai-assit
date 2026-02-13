/**
 * Swiss Cottages Chatbot Widget
 * Auto-initializes when script loads
 */

(function () {
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

            // Voice recording state
            this.isRecording = false;
            this.isProcessingAudio = false;
            this.isWaitingForResponse = false; // Track if we're waiting for LLM response
            this.isPlayingTTS = false; // Track if TTS audio is currently playing
            this.mediaRecorder = null;
            this.audioChunks = [];
            this.websocket = null;
            this.audioContext = null;
            this.audioStream = null;
            this.audioProcessor = null;
            this.audioBuffer = []; // For Web Audio API recording (PCM data)
            this.silenceTimer = null;
            this.currentAudio = null;
            this.voiceDetected = false; // Track if we've detected actual human voice
            this.mediaRecorderStopped = false; // Track if MediaRecorder has fully stopped
            this.pendingProcess = null; // Track pending process after stop
            this.recordingStartTime = null; // Track when recording started
            this.consecutiveNoiseCount = 0; // Track consecutive noise detections to reduce logging
            this.lastNoiseType = null; // Track last noise type to avoid duplicate logs

            // Advanced voice detection improvements
            this.backgroundNoiseLevel = 0.0; // Track background noise level
            this.noiseSamples = []; // Store noise samples for calibration
            this.isCalibrating = true; // Calibration phase (first 2 seconds)
            this.voiceHistory = []; // Track voice detection over time for temporal continuity
            this.fftAnalyzer = null; // FFT analyzer node for frequency analysis
            this.fftSize = 2048; // FFT size for frequency analysis

            // Real-time speech recognition
            this.speechRecognition = null;
            this.realTimeTranscript = ''; // Current transcript being built
            this.interimTranscript = ''; // Interim results from speech recognition
            this.interruptionSpeechHistory = []; // Track speech detections for interruption (must be sustained)

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
            // Call asynchronously to not block initialization
            this.clearBackendSession(sessionId).catch(() => {
                // Ignore errors - this is just cleanup
            });

            return sessionId;
        }

        async clearBackendSession(sessionId) {
            // Clear backend session to ensure fresh start
            // Use a dummy old session ID to clear any potential old sessions
            try {
                // Try to clear any existing session (ignore errors if session doesn't exist)
                await fetch(`${this.apiUrl}/api/chat/clear`, {
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

                // Update icon to fullscreen

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
            try {
                // Create widget container
                const widget = document.createElement('div');
                widget.id = 'chatbot-widget';
                widget.className = `chatbot-widget chatbot-${this.position}`;
                widget.innerHTML = `
                <button id="chatbot-toggle" class="chatbot-toggle" aria-label="Open chat">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display: block; color: white; stroke: currentColor;">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" style="fill: none; stroke: currentColor;"></path>
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
                            <button id="chatbot-voice" class="chatbot-voice" aria-label="Voice input" title="Voice input">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                                    <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                                    <line x1="12" y1="19" x2="12" y2="23"></line>
                                    <line x1="8" y1="23" x2="16" y2="23"></line>
                                </svg>
                            </button>
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

                // Ensure body exists before appending
                if (!document.body) {
                    console.error('Document body not found, waiting...');
                    setTimeout(() => this.initUI(), 100);
                    return;
                }

                document.body.appendChild(widget);
                console.log('Chatbot widget element appended to DOM', widget);

                // Show welcome screen initially
                this.showWelcomeScreen();
                console.log('Chatbot widget UI initialized successfully');
            } catch (error) {
                console.error('Error initializing chatbot UI:', error);
                // Still try to create a minimal widget if UI creation fails
                if (document.body) {
                    const fallbackWidget = document.createElement('div');
                    fallbackWidget.id = 'chatbot-widget';
                    fallbackWidget.className = `chatbot-widget chatbot-${this.position}`;
                    fallbackWidget.innerHTML = '<button id="chatbot-toggle" class="chatbot-toggle">💬</button>';
                    document.body.appendChild(fallbackWidget);
                }
            }
        }

        bindEvents() {
            const toggle = document.getElementById('chatbot-toggle');
            const close = document.getElementById('chatbot-close');
            const send = document.getElementById('chatbot-send');
            const voice = document.getElementById('chatbot-voice');
            const input = document.getElementById('chatbot-input');
            const menuBtn = document.getElementById('chatbot-menu');
            const menuDropdown = document.getElementById('chatbot-menu-dropdown');
            const restartBtn = document.getElementById('chatbot-restart');
            const fullscreenBtn = document.getElementById('chatbot-fullscreen');

            toggle.addEventListener('click', () => this.toggleChat());
            close.addEventListener('click', () => this.toggleChat());
            send.addEventListener('click', () => this.sendMessage());
            if (voice) {
                voice.addEventListener('click', () => this.toggleRecording());
            }

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

                // Ensure header is visible
                const header = chatWindow.querySelector('.chatbot-header');
                if (header) {
                    header.style.display = 'flex';
                    header.style.visibility = 'visible';
                    header.style.opacity = '1';

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

        showListeningMessage() {
            // Remove any existing listening message
            this.hideListeningMessage();

            const messagesContainer = document.getElementById('chatbot-messages');
            const listeningDiv = document.createElement('div');
            listeningDiv.id = 'chatbot-listening';
            listeningDiv.className = 'chatbot-message chatbot-message-assistant chatbot-listening';
            listeningDiv.innerHTML = `
                <div class="chatbot-message-content">
                    <div>🎤 Listening...</div>
                    <div id="chatbot-realtime-transcript" style="margin-top: 8px; color: #666; font-style: italic; min-height: 20px;"></div>
                </div>
            `;
            messagesContainer.appendChild(listeningDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        hideListeningMessage() {
            const listening = document.getElementById('chatbot-listening');
            if (listening) {
                listening.remove();
            }
        }

        updateRealTimeTranscript(text) {
            const transcriptDiv = document.getElementById('chatbot-realtime-transcript');
            if (transcriptDiv) {
                if (text && text.trim()) {
                    transcriptDiv.textContent = text;
                    transcriptDiv.style.color = '#333';
                } else {
                    transcriptDiv.textContent = '';
                }
            }
        }

        clearRealTimeTranscript() {
            this.realTimeTranscript = '';
            this.interimTranscript = '';
            this.updateRealTimeTranscript('');
        }

        initSpeechRecognition() {
            // Check if browser supports Web Speech API
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                console.log('⚠️ Web Speech API not supported in this browser');
                return;
            }

            try {
                this.speechRecognition = new SpeechRecognition();
                this.speechRecognition.continuous = true; // Keep listening continuously
                this.speechRecognition.interimResults = true; // Get interim results for real-time display
                this.speechRecognition.lang = 'en-US'; // Set language

                // Handle results
                this.speechRecognition.onresult = (event) => {
                    if (!this.isRecording || this.isWaitingForResponse) {
                        return;
                    }

                    let interimTranscript = '';
                    let finalTranscript = '';

                    // Process all results
                    for (let i = event.resultIndex; i < event.results.length; i++) {
                        const transcript = event.results[i][0].transcript;
                        if (event.results[i].isFinal) {
                            finalTranscript += transcript + ' ';
                        } else {
                            interimTranscript += transcript;
                        }
                    }

                    // Update real-time transcript display
                    if (finalTranscript) {
                        this.realTimeTranscript += finalTranscript;
                        this.interimTranscript = '';
                    } else {
                        this.interimTranscript = interimTranscript;
                    }

                    // Display combined transcript
                    const displayText = this.realTimeTranscript + this.interimTranscript;
                    this.updateRealTimeTranscript(displayText);
                };

                // Handle errors
                this.speechRecognition.onerror = (event) => {
                    console.error('Speech recognition error:', event.error);
                    // Don't stop recording on error, just log it
                };

                // Handle end (restart if still recording)
                this.speechRecognition.onend = () => {
                    if (this.isRecording && !this.isWaitingForResponse) {
                        // Restart recognition if still recording
                        try {
                            this.speechRecognition.start();
                        } catch (e) {
                            // Already started or error, ignore
                        }
                    }
                };

                // Start recognition
                this.speechRecognition.start();
                console.log('✅ Real-time speech recognition started');
            } catch (error) {
                console.error('Error initializing speech recognition:', error);
            }
        }

        showThinkingMessage() {
            // Hide listening message if it exists
            this.hideListeningMessage();

            // Show thinking message (reuse existing showLoading)
            this.showLoading();
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

            // Show loading
            this.showLoading();


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

                // Check if response is streaming (text/event-stream) or JSON
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('text/event-stream')) {
                    // Read stream
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) {
                            // Stream ended - make sure loading is hidden
                            this.hideLoading();
                            this.hideSearching();
                            break;
                        }

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

                                        // CRITICAL: Hide loading to allow next query
                                        this.hideLoading();
                                        this.hideSearching();

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
                } else {
                    // Handle JSON response (non-streaming)
                    const data = await response.json();
                    console.log('API Response:', data);
                    console.log('Cottage images:', data.cottage_images);
                    this.hideLoading();
                    this.addMessage(
                        'assistant',
                        data.answer,
                        data.sources,
                        data.cottage_images || null
                    );
                }
            } catch (error) {
                console.error('Error sending message:', error);
                this.hideLoading();
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

        // ==================== Voice Recording Methods ====================

        async toggleRecording() {
            // Toggle recording: start if not recording, stop if recording
            if (this.isRecording) {
                await this.stopRecording();
            } else {
                await this.startRecording();
            }
        }

        async startRecording() {
            // If already recording, reset state but don't reinitialize everything
            if (this.isRecording && this.audioContext && this.audioContext.state === 'running') {
                // Reset state for new recording session
                this.audioBuffer = [];
                this.voiceDetected = false;
                this.isProcessingAudio = false;
                this.isWaitingForResponse = false;
                this.recordingStartTime = Date.now();
                console.log('🔄 Recording already active - resetting state for new session');
                return;
            }

            try {
                // Get audio stream
                if (!this.audioStream) {
                    this.audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                }

                this.isRecording = true;
                this.recordingStartTime = Date.now();

                // Update UI
                const voiceBtn = document.getElementById('chatbot-voice');
                if (voiceBtn) {
                    voiceBtn.classList.add('recording');
                }

                // Hide welcome screen when voice conversation starts (same as text)
                this.hideWelcomeScreen();

                // Show "Listening..." message in chat
                this.showListeningMessage();

                // Initialize WebSocket connection if not already connected
                if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
                    await this.connectWebSocket();
                }

                // Initialize Web Audio API
                if (!this.audioContext) {
                    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
                }

                // Resume audio context if suspended
                if (this.audioContext.state === 'suspended') {
                    await this.audioContext.resume();
                }

                // Create audio source from stream
                const source = this.audioContext.createMediaStreamSource(this.audioStream);

                // Create FFT analyzer for frequency analysis (if not already created)
                if (!this.fftAnalyzer) {
                    this.fftAnalyzer = this.audioContext.createAnalyser();
                    this.fftAnalyzer.fftSize = this.fftSize;
                    this.fftAnalyzer.smoothingTimeConstant = 0.3;
                }

                // Connect source to analyzer for frequency analysis
                source.connect(this.fftAnalyzer);

                // Create script processor to capture audio data
                const bufferSize = 4096;
                this.audioProcessor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

                // Connect source to processor for audio capture
                source.connect(this.audioProcessor);
                this.audioProcessor.connect(this.audioContext.destination);

                // Clear audio buffer
                this.audioBuffer = [];
                this.voiceDetected = false;

                // Reset calibration and voice history for new recording session
                this.backgroundNoiseLevel = 0.0;
                this.noiseSamples = [];
                this.isCalibrating = true;
                this.voiceHistory = [];
                this.realTimeTranscript = '';
                this.interimTranscript = '';
                this.interruptionSpeechHistory = [];

                // Initialize Web Speech API for real-time word detection
                this.initSpeechRecognition();

                // Process audio data
                this.audioProcessor.onaudioprocess = (event) => {
                    // Always process audio if recording (even during TTS for interruption detection)
                    if (!this.isRecording) {
                        return;
                    }

                    const inputData = event.inputBuffer.getChannelData(0);

                    // Advanced voice detection to filter out noise
                    const voiceCheck = this.detectHumanSpeech(inputData);

                    // If TTS is playing, only check for user interruption (don't collect audio into buffer)
                    // This prevents the agent from listening to its own voice
                    // IMPORTANT: Audio processor must continue running during TTS to detect interruptions
                    if (this.isPlayingTTS) {
                        // Debug: Log occasionally to confirm audio processor is running during TTS
                        if (Math.random() < 0.01) { // Log 1% of the time to avoid spam
                            console.log('🔍 Audio processor active during TTS - checking for interruptions...');
                        }
                        // STRICT interruption detection during TTS - ONLY accept confirmed human speech
                        // This prevents interrupting on random noise/voices
                        const currentTime = Date.now();

                        // ONLY check for confirmed human speech - reject all noise/random voices
                        const isConfirmedSpeech = voiceCheck.isHumanSpeech && voiceCheck.confidence >= 0.35; // Lowered slightly for responsiveness
                        const hasGoodRMS = voiceCheck.rms > 0.04; // Minimum RMS for valid speech

                        // Debug logging (only occasionally to avoid spam)
                        if (isConfirmedSpeech) {
                            if (Math.random() < 0.2) { // Log 20% of the time when speech detected
                                console.log('🔍 Interruption check - RMS:', voiceCheck.rms.toFixed(4), 'isHumanSpeech:', voiceCheck.isHumanSpeech, 'confidence:', voiceCheck.confidence.toFixed(2));
                            }
                        }

                        // ONLY process if it's confirmed human speech with good RMS
                        if (isConfirmedSpeech && hasGoodRMS) {
                            // Add to interruption speech history
                            this.interruptionSpeechHistory.push({
                                time: currentTime,
                                rms: voiceCheck.rms,
                                confidence: voiceCheck.confidence,
                                isHumanSpeech: voiceCheck.isHumanSpeech
                            });

                            // Remove old history (older than 0.6 seconds - faster response)
                            this.interruptionSpeechHistory = this.interruptionSpeechHistory.filter(
                                entry => currentTime - entry.time < 600
                            );

                            // Interrupt immediately if:
                            // 1. High energy confirmed speech (RMS > 0.05 and isHumanSpeech), OR
                            // 2. At least 1 confirmed speech detection with good confidence (>= 0.40)
                            const highEnergyInterrupt = voiceCheck.rms > 0.05 && voiceCheck.isHumanSpeech && voiceCheck.confidence >= 0.40;
                            const sustainedSpeech = this.interruptionSpeechHistory.length >= 1 && voiceCheck.confidence >= 0.40;

                            if (highEnergyInterrupt || sustainedSpeech) {
                                // Calculate average confidence
                                const avgConfidence = this.interruptionSpeechHistory.length > 0
                                    ? this.interruptionSpeechHistory.reduce(
                                        (sum, entry) => sum + entry.confidence, 0
                                    ) / this.interruptionSpeechHistory.length
                                    : voiceCheck.confidence;

                                console.log('🛑 User interruption detected during TTS playback - RMS:', voiceCheck.rms.toFixed(4), 'Confidence:', avgConfidence.toFixed(2), 'Detections:', this.interruptionSpeechHistory.length, 'stopping agent speech');
                                this.cancelProcessing();
                                // Start collecting new audio from this point
                                const buffer = new Float32Array(inputData.length);
                                buffer.set(inputData);
                                this.audioBuffer = [buffer];
                                this.voiceDetected = true;
                                this.interruptionSpeechHistory = []; // Reset after interruption
                                this.startSilenceTimer();
                                // Exit early - don't return, continue to collect audio
                            }
                        } else {
                            // Not confirmed human speech - clear interruption history if no activity for a while
                            if (this.interruptionSpeechHistory.length > 0) {
                                const lastDetection = this.interruptionSpeechHistory[this.interruptionSpeechHistory.length - 1];
                                if (currentTime - lastDetection.time > 300) {
                                    // Clear if no activity for 300ms (faster clearing)
                                    this.interruptionSpeechHistory = [];
                                }
                            }
                        }
                        // Don't collect audio during TTS - prevents listening to own voice
                        return;
                    }

                    // Don't collect audio if waiting for LLM response (but still process for interruption)
                    if (this.isWaitingForResponse) {
                        return;
                    }

                    // Normal recording mode - collect audio and detect voice
                    const buffer = new Float32Array(inputData.length);
                    buffer.set(inputData);
                    this.audioBuffer.push(buffer);

                    // MUCH MORE LENIENT: Set voiceDetected if:
                    // 1. Confirmed human speech (isHumanSpeech && confidence >= 0.30 && RMS > 0.03), OR
                    // 2. High RMS (>= 0.05) - indicates significant sound/voice, OR
                    // 3. Moderate RMS (>= 0.03) with any confidence - allows quieter speech
                    const isConfirmedHumanSpeech = voiceCheck.isHumanSpeech && voiceCheck.confidence >= 0.30 && voiceCheck.rms > 0.03;
                    const hasHighRMS = voiceCheck.rms >= 0.05; // High RMS indicates voice
                    const hasModerateRMS = voiceCheck.rms >= 0.03; // Moderate RMS with any confidence

                    if (isConfirmedHumanSpeech || hasHighRMS || hasModerateRMS) {
                        this.voiceDetected = true;
                        this.consecutiveNoiseCount = 0; // Reset noise counter when speech detected
                        const totalSamples = this.audioBuffer.reduce((sum, buf) => sum + buf.length, 0);
                        const duration = totalSamples / this.audioContext.sampleRate;
                        const reason = isConfirmedHumanSpeech ? 'confirmed' : (hasHighRMS ? 'high RMS' : 'moderate RMS');
                        console.log('🎤 Human speech detected - Confidence:', voiceCheck.confidence.toFixed(2), 'RMS:', voiceCheck.rms.toFixed(4), 'duration:', duration.toFixed(2), 's', `(${reason})`);

                        // Restart silence timer on meaningful voice
                        if (!this.isProcessingAudio) {
                            this.startSilenceTimer();
                        }
                    } else if (voiceCheck.rms > 0.01) {
                        // There's some sound but it's not human speech
                        this.consecutiveNoiseCount++;

                        // Only log noise occasionally to reduce console spam:
                        // - First noise detection
                        // - Every 50th noise detection
                        // - When noise type changes
                        // - When noise stops (after 10 consecutive detections)
                        const shouldLog =
                            this.consecutiveNoiseCount === 1 ||
                            this.consecutiveNoiseCount % 50 === 0 ||
                            this.lastNoiseType !== voiceCheck.noiseType ||
                            (this.consecutiveNoiseCount === 10);

                        if (shouldLog) {
                            if (this.consecutiveNoiseCount === 1) {
                                console.log('🔇 Background noise detected:', voiceCheck.noiseType, '(suppressing further noise logs)');
                            } else if (this.consecutiveNoiseCount % 50 === 0) {
                                console.log('🔇 Still detecting noise:', voiceCheck.noiseType, `(${this.consecutiveNoiseCount} consecutive)`);
                            } else if (this.lastNoiseType !== voiceCheck.noiseType) {
                                console.log('🔇 Noise type changed:', this.lastNoiseType, '→', voiceCheck.noiseType);
                            }
                        }

                        this.lastNoiseType = voiceCheck.noiseType;
                    } else {
                        // Very quiet - reset noise counter
                        if (this.consecutiveNoiseCount > 0) {
                            this.consecutiveNoiseCount = 0;
                            this.lastNoiseType = null;
                        }
                    }
                };

                // Connect audio nodes
                // Note: We connect processor to destination for monitoring, but will disconnect during TTS
                source.connect(this.audioProcessor);
                this.audioProcessor.connect(this.audioContext.destination);

                // Store source for later disconnection during TTS
                this.audioSource = source;

                // Start silence detection after a short delay
                setTimeout(() => {
                    if (this.isRecording && !this.isProcessingAudio) {
                        this.startSilenceTimer();
                    }
                }, 500);

            } catch (error) {
                console.error('Error starting recording:', error);
                this.isRecording = false;
                alert('Could not access microphone. Please check permissions.');
            }
        }

        async stopRecording() {
            // Clear silence timer first to prevent processing
            if (this.silenceTimer) {
                clearTimeout(this.silenceTimer);
                this.silenceTimer = null;
            }

            // Stop speech recognition
            if (this.speechRecognition) {
                this.speechRecognition.stop();
                this.speechRecognition = null;
            }

            // Disconnect audio processor (but don't process audio - user manually stopped)
            if (this.audioProcessor) {
                this.audioProcessor.disconnect();
                this.audioProcessor = null;
            }

            // Clear audio buffer since user manually stopped
            this.audioBuffer = [];

            // Stop stream tracks
            if (this.audioStream) {
                this.audioStream.getTracks().forEach(track => track.stop());
                this.audioStream = null;
            }

            this.isRecording = false;

            const voiceBtn = document.getElementById('chatbot-voice');
            if (voiceBtn) {
                voiceBtn.classList.remove('recording');
            }

            // Hide listening message and clear transcript
            this.hideListeningMessage();
            this.clearRealTimeTranscript();
        }

        async restartRecording() {
            if (!this.isRecording) {
                return;
            }

            // Don't restart if we're still waiting for response
            if (this.isWaitingForResponse) {
                console.log('⚠️ Cannot restart recording - still waiting for response');
                return;
            }

            // Clear previous audio buffer and reset voice detection state
            this.audioBuffer = [];
            this.voiceDetected = false;
            this.isProcessingAudio = false;

            // Small delay to ensure audio context is ready
            await new Promise(resolve => setTimeout(resolve, 100));

            // If audio context is still active, just restart silence timer
            if (this.audioContext && this.audioContext.state === 'running') {
                this.startSilenceTimer();
                console.log('🔄 Recording already active, restarted silence timer');
            } else {
                // Need to restart recording
                console.log('🔄 Restarting recording...');
                await this.startRecording();
            }
        }

        startSilenceTimer() {
            if (this.silenceTimer) {
                clearTimeout(this.silenceTimer);
            }

            // Don't start silence timer if TTS is playing (unless we just interrupted)
            // If voiceDetected is true, it means user interrupted, so allow timer
            if (this.isPlayingTTS && !this.voiceDetected) {
                console.log('⚠️ Cannot start silence timer - TTS is playing');
                return;
            }

            this.silenceTimer = setTimeout(() => {
                console.log('⏰ Silence timer fired after 2 seconds');

                // Only process if:
                // 1. We have audio buffers
                // 2. We have enough audio data (at least 0.5 seconds)
                // 3. We're not already processing
                // 4. TTS is not playing (don't process during agent speech)
                // Note: We'll check voice detection in handleSilenceDetected, but allow processing if we have reasonable audio
                if (this.audioBuffer.length > 0 && !this.isProcessingAudio && !this.isPlayingTTS) {
                    const totalSamples = this.audioBuffer.reduce((sum, buf) => sum + buf.length, 0);
                    const minSamples = this.audioContext ? (this.audioContext.sampleRate * 0.5) : 16000; // At least 0.5 seconds
                    const duration = totalSamples / (this.audioContext ? this.audioContext.sampleRate : 16000);

                    // Calculate average RMS of audio buffers to check if there's reasonable audio
                    let totalRMS = 0;
                    let rmsCount = 0;
                    for (const buf of this.audioBuffer) {
                        const rms = this.calculateRMS(buf);
                        totalRMS += rms;
                        rmsCount++;
                    }
                    const avgRMS = rmsCount > 0 ? totalRMS / rmsCount : 0;

                    console.log('📊 Audio stats:', {
                        buffers: this.audioBuffer.length,
                        totalSamples: totalSamples,
                        duration: duration.toFixed(2) + 's',
                        voiceDetected: this.voiceDetected,
                        avgRMS: avgRMS.toFixed(4),
                        minRequired: minSamples
                    });

                    // Process if we have enough audio AND either:
                    // 1. Voice was detected, OR
                    // 2. Average RMS is reasonable (>= 0.02) - indicates there was some sound
                    if (totalSamples >= minSamples && (this.voiceDetected || avgRMS >= 0.02)) {
                        console.log('🔇 2 seconds of silence detected, processing audio...', this.audioBuffer.length, 'buffers, total samples:', totalSamples, 'voiceDetected:', this.voiceDetected, 'avgRMS:', avgRMS.toFixed(4));
                        this.handleSilenceDetected();
                    } else {
                        console.log('⚠️ Silence detected but:', {
                            totalSamples: totalSamples,
                            minRequired: minSamples,
                            voiceDetected: this.voiceDetected,
                            avgRMS: avgRMS.toFixed(4),
                            reason: totalSamples < minSamples ? 'audio too short (need 0.5s)' : (avgRMS < 0.02 ? 'RMS too low (likely silence)' : 'no voice detected')
                        });
                        // Reset and continue recording
                        this.audioBuffer = [];
                        this.voiceDetected = false;
                        if (this.isRecording && !this.isProcessingAudio) {
                            this.startSilenceTimer(); // Restart timer
                        }
                    }
                } else {
                    console.log('⚠️ Silence timer fired but not processing:', {
                        buffers: this.audioBuffer.length,
                        processing: this.isProcessingAudio,
                        recording: this.isRecording,
                        voiceDetected: this.voiceDetected,
                        isPlayingTTS: this.isPlayingTTS
                    });
                    // Reset if no voice was detected and no reasonable audio
                    if (!this.voiceDetected && this.audioBuffer.length > 0) {
                        // Check RMS before clearing
                        let totalRMS = 0;
                        for (const buf of this.audioBuffer) {
                            totalRMS += this.calculateRMS(buf);
                        }
                        const avgRMS = this.audioBuffer.length > 0 ? totalRMS / this.audioBuffer.length : 0;
                        if (avgRMS < 0.02) {
                            this.audioBuffer = [];
                        }
                    } else if (!this.voiceDetected) {
                        this.audioBuffer = [];
                    }
                    // Restart timer if we're still recording and not processing
                    if (this.isRecording && !this.isProcessingAudio) {
                        console.log('🔄 Restarting silence timer...');
                        this.startSilenceTimer();
                    }
                }
                this.silenceTimer = null;
            }, 2000);
        }

        handleSilenceDetected() {
            // Don't process if we're waiting for a response
            if (this.isWaitingForResponse) {
                console.log('⚠️ Silence detected but waiting for response, ignoring...');
                return;
            }

            // If processing, cancel it and restart listening
            if (this.isProcessingAudio) {
                console.log('🛑 User interruption detected - stopping agent and processing');
                this.cancelProcessing();
                return;
            }

            // Process if we have audio buffers (voice detection will be checked in processAudioChunks)
            if (this.audioBuffer.length === 0) {
                console.log('⚠️ Silence detected but no audio buffers to process');
                // Reset and continue
                this.audioBuffer = [];
                this.voiceDetected = false;
                return;
            }

            // Calculate average RMS to verify there's reasonable audio
            let totalRMS = 0;
            for (const buf of this.audioBuffer) {
                totalRMS += this.calculateRMS(buf);
            }
            const avgRMS = this.audioBuffer.length > 0 ? totalRMS / this.audioBuffer.length : 0;

            // Process if we have reasonable audio (RMS >= 0.02) even if voiceDetected is false
            // The validation in processAudioChunks will do the final check
            if (avgRMS < 0.02 && !this.voiceDetected) {
                console.log('⚠️ Silence detected but audio RMS too low:', avgRMS.toFixed(4), 'voiceDetected:', this.voiceDetected);
                this.audioBuffer = [];
                this.voiceDetected = false;
                return;
            }

            // Process audio directly (Web Audio API doesn't need to stop like MediaRecorder)
            console.log('🛑 Processing audio from Web Audio API...');
            console.log('📊 Pre-processing check - voiceDetected:', this.voiceDetected, 'buffers:', this.audioBuffer.length, 'avgRMS:', avgRMS.toFixed(4));
            this.processAudioChunks();
        }

        // Calibrate background noise during first 2 seconds
        calibrateBackgroundNoise(audioData) {
            if (this.isCalibrating && this.noiseSamples.length < 100) {
                const rms = this.calculateRMS(audioData);
                this.noiseSamples.push(rms);

                if (this.noiseSamples.length >= 100) {
                    // Calculate median noise level (more robust than mean)
                    const sorted = [...this.noiseSamples].sort((a, b) => a - b);
                    this.backgroundNoiseLevel = sorted[50]; // Median
                    this.isCalibrating = false;
                    console.log('🎯 Background noise calibrated:', this.backgroundNoiseLevel.toFixed(4));
                }
            }
        }

        // Calculate RMS (Root Mean Square) energy
        calculateRMS(audioData) {
            if (!audioData || audioData.length === 0) return 0.0;
            let sum = 0;
            for (let i = 0; i < audioData.length; i++) {
                sum += audioData[i] * audioData[i];
            }
            return Math.sqrt(sum / audioData.length);
        }

        // Calculate frequency features using AnalyserNode if available, otherwise use autocorrelation
        calculateFrequencyFeatures(audioData, sampleRate) {
            const features = {
                speechBandEnergy: 0.0,
                totalEnergy: 0.0,
                speechRatio: 0.0,
                spectralCentroid: 0.0,
                spectralRolloff: 0.0
            };

            try {
                // Use AnalyserNode if available and connected
                // Note: FFT analyzer might not have data yet, so we'll use fallback
                if (this.fftAnalyzer && this.fftAnalyzer.frequencyBinCount > 0) {
                    const frequencyData = new Uint8Array(this.fftAnalyzer.frequencyBinCount);
                    this.fftAnalyzer.getByteFrequencyData(frequencyData);

                    // Check if we actually have data (not all zeros)
                    const hasData = frequencyData.some(val => val > 0);
                    if (!hasData) {
                        // FFT analyzer not receiving data, use fallback
                        throw new Error('FFT analyzer has no data');
                    }

                    // Speech energy is concentrated in 300-3400 Hz range
                    const speechMinFreq = 300;  // Hz
                    const speechMaxFreq = 3400; // Hz
                    const fftSize = this.fftAnalyzer.fftSize;
                    const speechMinBin = Math.floor(speechMinFreq * fftSize / sampleRate);
                    const speechMaxBin = Math.floor(speechMaxFreq * fftSize / sampleRate);

                    let weightedSum = 0;
                    let magnitudeSum = 0;

                    for (let i = 0; i < frequencyData.length; i++) {
                        const magnitude = frequencyData[i];
                        const frequency = (i * sampleRate) / (fftSize * 2);
                        features.totalEnergy += magnitude;

                        if (i >= speechMinBin && i <= speechMaxBin) {
                            features.speechBandEnergy += magnitude;
                        }

                        weightedSum += frequency * magnitude;
                        magnitudeSum += magnitude;
                    }

                    features.speechRatio = features.totalEnergy > 0
                        ? features.speechBandEnergy / features.totalEnergy
                        : 0.0;
                    features.spectralCentroid = magnitudeSum > 0
                        ? weightedSum / magnitudeSum
                        : 0.0;

                    // Calculate spectral rolloff (85% of energy)
                    const rolloffPercent = 0.85;
                    const targetEnergy = features.totalEnergy * rolloffPercent;
                    let cumulativeEnergy = 0;
                    for (let i = 0; i < frequencyData.length; i++) {
                        cumulativeEnergy += frequencyData[i];
                        if (cumulativeEnergy >= targetEnergy) {
                            features.spectralRolloff = (i * sampleRate) / (fftSize * 2);
                            break;
                        }
                    }
                } else {
                    // Fallback: Use autocorrelation for fundamental frequency estimation
                    // This is faster than full DFT and gives reasonable estimates
                    try {
                        const autocorr = this.autocorrelation(audioData);
                        const fundamentalFreq = this.findFundamentalFrequency(autocorr, sampleRate);

                        // Estimate speech features from fundamental frequency
                        // Speech typically has fundamental frequency 80-300 Hz
                        if (fundamentalFreq >= 80 && fundamentalFreq <= 300) {
                            features.speechRatio = 0.6; // Likely speech
                            features.spectralCentroid = fundamentalFreq * 7; // Approximate (formants are ~7x fundamental)
                            features.spectralRolloff = fundamentalFreq * 12; // Approximate
                        } else if (fundamentalFreq > 0) {
                            // Some frequency detected but not in speech range
                            features.speechRatio = 0.4; // Moderate likelihood
                            features.spectralCentroid = fundamentalFreq * 7;
                            features.spectralRolloff = fundamentalFreq * 12;
                        } else {
                            // No clear fundamental frequency - use neutral values
                            features.speechRatio = 0.5; // Neutral - don't reject
                            features.spectralCentroid = 1750; // Typical speech
                            features.spectralRolloff = 3000; // Typical speech
                        }
                    } catch (error) {
                        // If autocorrelation fails, use neutral values (don't reject)
                        features.speechRatio = 0.5;
                        features.spectralCentroid = 1750;
                        features.spectralRolloff = 3000;
                    }
                }

            } catch (error) {
                // Fallback: Simple approximation
                features.speechRatio = 0.5;
                features.spectralCentroid = 1750;
                features.spectralRolloff = 3000;
            }

            return features;
        }

        // Autocorrelation for fundamental frequency detection
        autocorrelation(signal) {
            const length = signal.length;
            const autocorr = new Float32Array(length);

            for (let lag = 0; lag < length; lag++) {
                let sum = 0;
                for (let i = 0; i < length - lag; i++) {
                    sum += signal[i] * signal[i + lag];
                }
                autocorr[lag] = sum / (length - lag);
            }

            return autocorr;
        }

        // Find fundamental frequency from autocorrelation
        findFundamentalFrequency(autocorr, sampleRate) {
            // Find first significant peak after the zero-lag peak
            const minPeriod = Math.floor(sampleRate / 400); // Max 400 Hz
            const maxPeriod = Math.floor(sampleRate / 80);  // Min 80 Hz

            let maxPeak = 0;
            let maxPeakIndex = 0;

            for (let i = minPeriod; i < Math.min(maxPeriod, autocorr.length); i++) {
                if (autocorr[i] > maxPeak) {
                    maxPeak = autocorr[i];
                    maxPeakIndex = i;
                }
            }

            return maxPeakIndex > 0 ? sampleRate / maxPeakIndex : 0;
        }

        // Advanced voice detection to filter out noise (button clicks, fan, traffic, etc.)
        detectHumanSpeech(audioData) {
            const result = {
                isHumanSpeech: false,
                confidence: 0.0,
                rms: 0.0,
                noiseType: 'none'
            };

            if (!audioData || audioData.length === 0) {
                return result;
            }

            const sampleRate = this.audioContext ? this.audioContext.sampleRate : 44100;
            const length = audioData.length;

            // 1. Calculate RMS (Root Mean Square) - basic energy level
            const rms = this.calculateRMS(audioData);
            result.rms = rms;

            // Calibrate background noise during first 2 seconds
            this.calibrateBackgroundNoise(audioData);

            // Use adaptive threshold (5x background noise, minimum 0.03 for better detection)
            // Lowered minimum to 0.03 to allow short words like "hello" while still filtering noise
            const adaptiveThreshold = Math.max(0.03, this.backgroundNoiseLevel * 5);

            // Minimum energy threshold - filter out very quiet sounds, clicks, and transient noises
            if (rms < adaptiveThreshold) {
                return result; // Too quiet, likely silence or noise
            }

            // 2. Zero Crossing Rate (ZCR) - speech has higher ZCR than noise
            let zeroCrossings = 0;
            for (let i = 1; i < length; i++) {
                if ((audioData[i] >= 0 && audioData[i - 1] < 0) ||
                    (audioData[i] < 0 && audioData[i - 1] >= 0)) {
                    zeroCrossings++;
                }
            }
            const zcr = zeroCrossings / length;

            // Speech typically has ZCR between 0.1 and 0.5
            // Button clicks have very high ZCR (>0.5) - made stricter
            // Fan/traffic noise has very low ZCR (<0.05)
            if (zcr > 0.5) {
                result.noiseType = 'click';
                return result; // Likely a button click or sharp sound
            }
            if (zcr < 0.05) {
                result.noiseType = 'constant_noise';
                return result; // Likely fan or constant background noise
            }

            // 3. Energy variance - speech has more variation than constant noise
            // Calculate mean first
            let mean = 0;
            for (let i = 0; i < length; i++) {
                mean += audioData[i];
            }
            mean = mean / length;

            // Calculate variance
            let variance = 0;
            for (let i = 0; i < length; i++) {
                variance += Math.pow(audioData[i] - mean, 2);
            }
            variance = variance / length;
            const energyVariance = Math.sqrt(variance);

            // Constant noise (fan, traffic) has low variance
            // Increased RMS threshold to 0.05 to match stricter validation
            if (energyVariance < 0.003 && rms < 0.05) {
                result.noiseType = 'constant_noise';
                return result; // Likely constant background noise
            }

            // 4. FFT-based Frequency Analysis - speech has energy in specific bands (300-3400 Hz)
            const freqFeatures = this.calculateFrequencyFeatures(audioData, sampleRate);

            // Only reject if frequency analysis is available and clearly indicates non-speech
            // Be very lenient - only reject if we have STRONG evidence it's not speech
            // If frequency analysis failed (returns defaults), don't reject based on it

            // Check if frequency analysis actually worked (not default values)
            const hasRealFrequencyData = freqFeatures.spectralCentroid > 0 &&
                freqFeatures.spectralCentroid !== 1750; // 1750 is default

            if (hasRealFrequencyData) {
                // Only reject if very clearly not speech
                if (freqFeatures.spectralCentroid < 100) {
                    // Extremely low frequency - likely not speech
                    result.noiseType = 'out_of_range';
                    return result;
                }

                // Stricter: reject if speech ratio is low (increased from 0.1 to 0.15)
                // This matches backend VAD's frequency filtering requirements
                if (freqFeatures.speechRatio > 0 && freqFeatures.speechRatio < 0.15) {
                    result.noiseType = 'low_speech_energy';
                    return result; // Low energy in speech band (300-3400 Hz)
                }

                // Spectral rolloff check - only reject if extremely abnormal
                if (freqFeatures.spectralRolloff > 0 && freqFeatures.spectralRolloff < 200) {
                    result.noiseType = 'abnormal_rolloff';
                    return result; // Extremely abnormal frequency distribution
                }
            }
            // If frequency analysis failed, don't reject - let other features decide

            // 5. Peak density analysis (time-domain fallback)
            let peaks = 0;
            let lastValue = audioData[0];
            let increasing = false;
            for (let i = 1; i < length; i++) {
                if (audioData[i] > lastValue && !increasing) {
                    increasing = true;
                } else if (audioData[i] < lastValue && increasing) {
                    peaks++;
                    increasing = false;
                }
                lastValue = audioData[i];
            }
            const peakDensity = peaks / length;

            // Speech has moderate peak density (0.1-0.3)
            // Button clicks have very high peak density (>0.35) - made stricter
            // Constant noise has very low peak density (<0.05)
            if (peakDensity > 0.35) {
                result.noiseType = 'click';
                return result; // Likely a click or sharp sound
            }
            if (peakDensity < 0.05 && rms < 0.05) {
                result.noiseType = 'constant_noise';
                return result; // Likely constant noise
            }

            // 6. Improved confidence scoring with normalized features
            let confidence = 0.0;

            // Normalize features first for better combination
            const normalizedRMS = Math.min(rms / 0.1, 1.0);
            const normalizedZCR = Math.max(0, Math.min(1, (zcr - 0.1) / 0.4));
            const normalizedVariance = Math.min(energyVariance / 0.02, 1.0);
            const normalizedPeakDensity = Math.max(0, Math.min(1, (peakDensity - 0.1) / 0.2));

            // Speech ratio normalization - be more lenient if frequency analysis failed
            let normalizedSpeechRatio = 0.5; // Default neutral value
            if (freqFeatures.speechRatio > 0) {
                normalizedSpeechRatio = Math.max(0, Math.min(1, (freqFeatures.speechRatio - 0.2) / 0.5));
            }

            // Spectral centroid contribution (speech: 1000-2500 Hz) - be more lenient
            let spectralScore = 0.5; // Default neutral value
            if (freqFeatures.spectralCentroid > 0) {
                if (freqFeatures.spectralCentroid >= 500 && freqFeatures.spectralCentroid <= 4000) {
                    // Accept wider range, give partial score
                    if (freqFeatures.spectralCentroid >= 1000 && freqFeatures.spectralCentroid <= 2500) {
                        spectralScore = 1.0 - Math.abs(freqFeatures.spectralCentroid - 1750) / 750;
                    } else {
                        // Outside ideal range but still reasonable
                        spectralScore = 0.3;
                    }
                    spectralScore = Math.max(0, Math.min(1, spectralScore));
                } else {
                    // Very far from speech range - but don't reject, just give low score
                    spectralScore = 0.2;
                }
            }

            // Weighted combination with better normalization
            confidence = (
                normalizedRMS * 0.25 +              // RMS: 25%
                normalizedZCR * 0.20 +              // ZCR: 20%
                normalizedVariance * 0.15 +        // Variance: 15%
                normalizedPeakDensity * 0.10 +      // Peak density: 10%
                normalizedSpeechRatio * 0.15 +      // Speech ratio: 15%
                spectralScore * 0.15                // Spectral centroid: 15%
            );

            // 7. Temporal Continuity - require sustained voice detection (more lenient for short words)
            const currentTime = Date.now();

            // Add to voice history if confidence is reasonable (lowered threshold for better detection)
            if (confidence >= 0.30) {
                this.voiceHistory.push({
                    time: currentTime,
                    confidence: confidence
                });
            }

            // Remove old history (older than 1.0 seconds - shorter window for faster detection)
            this.voiceHistory = this.voiceHistory.filter(
                entry => currentTime - entry.time < 1000
            );

            // More lenient: require at least 2 detections in last 1.0 seconds (reduced from 4)
            // OR if confidence is very high (>0.70), require at least 1 detection
            // This allows short words like "hello" to be detected
            if (confidence < 0.70 && this.voiceHistory.length < 2) {
                result.noiseType = 'too_brief';
                result.confidence = confidence;
                return result; // Too brief to be speech
            }
            if (confidence >= 0.70 && this.voiceHistory.length < 1) {
                result.noiseType = 'too_brief';
                result.confidence = confidence;
                return result; // Even high confidence needs at least one detection
            }

            // Calculate average confidence over time
            let avgConfidence = confidence;
            if (this.voiceHistory.length > 0) {
                avgConfidence = this.voiceHistory.reduce(
                    (sum, entry) => sum + entry.confidence, 0
                ) / this.voiceHistory.length;
            }

            // Use dynamic threshold based on background noise (more lenient for better detection)
            // Lowered minimum to 0.45 to allow short words like "hello" to be detected
            const dynamicThreshold = Math.max(0.45, 0.45 + (this.backgroundNoiseLevel * 10));

            // Final decision: combine current confidence with temporal average
            // If we have history, use weighted average; otherwise use current confidence
            const finalConfidence = this.voiceHistory.length >= 2
                ? (confidence * 0.6) + (avgConfidence * 0.4)
                : confidence;

            // Additional check: require minimum RMS even if confidence is high
            // This prevents low-energy clicks from being accepted
            // Lowered to 0.03 to allow short words like "hello" (but still reject clicks)
            const minRMSForSpeech = 0.03; // Minimum RMS for actual speech (more lenient)

            if (finalConfidence >= dynamicThreshold && rms >= minRMSForSpeech) {
                result.isHumanSpeech = true;
                result.confidence = Math.min(finalConfidence, 1.0);
                // Debug logging for successful detection
                if (Math.random() < 0.1) { // Log 10% of detections to avoid spam
                    console.log('✅ Speech detected - RMS:', rms.toFixed(4), 'Confidence:', finalConfidence.toFixed(2), 'Threshold:', dynamicThreshold.toFixed(2), 'History:', this.voiceHistory.length);
                }
            } else {
                result.noiseType = 'low_confidence';
                result.confidence = finalConfidence;
                // Debug logging for rejected detection
                if (rms > 0.02 && Math.random() < 0.05) { // Log 5% of rejections with reasonable RMS
                    console.log('❌ Speech rejected - RMS:', rms.toFixed(4), 'Confidence:', finalConfidence.toFixed(2), 'Threshold:', dynamicThreshold.toFixed(2), 'MinRMS:', minRMSForSpeech.toFixed(3), 'History:', this.voiceHistory.length, 'Reason:', finalConfidence < dynamicThreshold ? 'low_confidence' : 'low_rms');
                }
            }

            return result;
        }

        // Convert Float32Array audio buffer to WAV format
        float32ArrayToWav(audioBuffer, sampleRate) {
            const length = audioBuffer.length;
            const buffer = new ArrayBuffer(44 + length * 2);
            const view = new DataView(buffer);
            const samples = new Int16Array(buffer, 44);

            // WAV header
            const writeString = (offset, string) => {
                for (let i = 0; i < string.length; i++) {
                    view.setUint8(offset + i, string.charCodeAt(i));
                }
            };

            writeString(0, 'RIFF');
            view.setUint32(4, 36 + length * 2, true);
            writeString(8, 'WAVE');
            writeString(12, 'fmt ');
            view.setUint32(16, 16, true);
            view.setUint16(20, 1, true);
            view.setUint16(22, 1, true);
            view.setUint32(24, sampleRate, true);
            view.setUint32(28, sampleRate * 2, true);
            view.setUint16(32, 2, true);
            view.setUint16(34, 16, true);
            writeString(36, 'data');
            view.setUint32(40, length * 2, true);

            // Convert float samples to 16-bit PCM
            for (let i = 0; i < length; i++) {
                const s = Math.max(-1, Math.min(1, audioBuffer[i]));
                samples[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }

            return buffer;
        }

        async processAudioChunks() {
            if (this.isProcessingAudio || this.audioBuffer.length === 0) {
                return;
            }

            this.isProcessingAudio = true;
            this.isWaitingForResponse = true; // Mark that we're waiting for response

            // Hide listening message and show thinking message
            this.hideListeningMessage();
            this.showThinkingMessage();

            console.log('🎤 Processing accumulated audio buffers...', this.audioBuffer.length, 'buffers');

            // Clear silence timer since we're processing
            if (this.silenceTimer) {
                clearTimeout(this.silenceTimer);
                this.silenceTimer = null;
            }

            try {
                // Combine all audio buffers into one Float32Array
                // Don't reject early - let validation check RMS and speech ratio instead
                const totalLength = this.audioBuffer.reduce((sum, buf) => sum + buf.length, 0);
                if (totalLength === 0) {
                    console.warn('⚠️ No audio data to process');
                    this.isProcessingAudio = false;
                    return;
                }

                const combinedBuffer = new Float32Array(totalLength);
                let offset = 0;
                for (const buffer of this.audioBuffer) {
                    combinedBuffer.set(buffer, offset);
                    offset += buffer.length;
                }

                // Additional validation: Check if the collected audio actually contains human speech
                const sampleRate = this.audioContext.sampleRate;
                const duration = totalLength / sampleRate;

                // Need at least 0.3 seconds of audio to be valid
                if (duration < 0.3) {
                    console.warn('⚠️ Audio too short:', duration.toFixed(2), 's (need at least 0.3s)');
                    this.isProcessingAudio = false;
                    this.isWaitingForResponse = false; // Reset waiting flag so recording can restart
                    this.voiceDetected = false;
                    this.audioBuffer = [];
                    // Hide messages
                    this.hideLoading();
                    this.hideListeningMessage();
                    // Restart recording immediately
                    if (this.isRecording) {
                        this.restartRecording();
                    }
                    return;
                }

                // Sample check: analyze a few chunks from the combined buffer
                // to ensure it's not just noise
                const chunkSize = Math.floor(sampleRate * 0.1); // 100ms chunks
                let validSpeechChunks = 0;
                let totalChunks = 0;
                let chunksWithVoice = 0; // Track chunks with any voice energy

                for (let i = 0; i < combinedBuffer.length - chunkSize; i += chunkSize) {
                    const chunk = combinedBuffer.slice(i, i + chunkSize);
                    const voiceCheck = this.detectHumanSpeech(chunk);
                    totalChunks++;
                    if (voiceCheck.isHumanSpeech) {
                        validSpeechChunks++;
                    }
                    // Count chunks with confirmed human speech (not just RMS - must be actual speech)
                    // Only count if it's confirmed human speech with good RMS
                    if (voiceCheck.isHumanSpeech && voiceCheck.confidence >= 0.35 && voiceCheck.rms > 0.04) {
                        chunksWithVoice++;
                    }
                }

                // STRICT: Only accept confirmed human speech - reject random noise/voices
                // At least 15% of chunks must contain confirmed human speech (or 10% if voice was detected)
                const speechRatio = validSpeechChunks / totalChunks;
                const voiceEnergyRatio = chunksWithVoice / totalChunks;

                // Process if:
                // 1. Voice was detected during recording (this.voiceDetected = true), AND
                // 2. Speech ratio >= 10% (more lenient for short utterances) OR speech ratio >= 15% (for longer speech)
                // More lenient: allow processing if RMS is reasonable even if voiceDetected is false
                // But still require some speech ratio to avoid pure noise
                const minSpeechRatio = this.voiceDetected ? 0.10 : 0.15; // More lenient if voice was detected

                // Calculate average RMS of the entire audio
                const avgRMS = this.calculateRMS(combinedBuffer);

                // If speech ratio is 0.00, voiceDetected flag is likely stale - reset it
                if (speechRatio === 0.00 && this.voiceDetected) {
                    console.log('⚠️ Speech ratio is 0.00 but voiceDetected is true - resetting voiceDetected flag');
                    this.voiceDetected = false;
                }

                // MUCH MORE LENIENT: Process if:
                // 1. Voice was detected, OR
                // 2. High RMS (>= 0.045) - indicates significant sound/voice, OR
                // 3. Moderate RMS (>= 0.02) with some speech (>= 3%)
                const hasHighRMS = avgRMS >= 0.045; // Lowered threshold slightly (was 0.05) to catch 0.0470
                const hasModerateRMS = avgRMS >= 0.02; // Moderate RMS
                const hasSomeSpeech = speechRatio >= 0.03; // At least 3% speech (very lenient)

                // If RMS is high, process regardless of voiceDetected or speech ratio
                if (hasHighRMS) {
                    console.log('✅ Processing audio with high RMS:', avgRMS.toFixed(4), '(high RMS indicates voice)');
                    // Set voiceDetected retroactively for high RMS
                    this.voiceDetected = true;
                } else if (!this.voiceDetected && !(hasModerateRMS && hasSomeSpeech)) {
                    console.warn('⚠️ Audio rejected - no voice detected and RMS/speech too low. Speech ratio:', speechRatio.toFixed(2), 'Voice energy ratio:', voiceEnergyRatio.toFixed(2), 'Avg RMS:', avgRMS.toFixed(4));
                    this.isProcessingAudio = false;
                    this.isWaitingForResponse = false;
                    this.voiceDetected = false;
                    this.audioBuffer = [];
                    this.hideLoading();
                    this.hideListeningMessage();
                    // Don't restart immediately - let silence timer handle it to avoid loops
                    if (this.isRecording && this.silenceTimer) {
                        // Timer is already running, just clear buffer and let it continue
                    } else if (this.isRecording) {
                        // Start a new timer after a short delay
                        setTimeout(() => {
                            if (this.isRecording && !this.isProcessingAudio) {
                                this.startSilenceTimer();
                            }
                        }, 500);
                    }
                    return;
                }

                // If voiceDetected is false but we have reasonable RMS and some speech, use lower threshold
                // Or if RMS is high, be very lenient with speech ratio
                // Also: if RMS is high (>= 0.045), don't require speech ratio at all
                const effectiveMinRatio = hasHighRMS ? 0.00 : (this.voiceDetected || (hasModerateRMS && hasSomeSpeech)) ? 0.10 : 0.15;

                if (speechRatio < effectiveMinRatio && !hasHighRMS) {
                    console.warn('⚠️ Audio contains mostly noise, not human speech. Speech ratio:', speechRatio.toFixed(2), 'Voice energy ratio:', voiceEnergyRatio.toFixed(2), 'Voice detected:', this.voiceDetected, 'Avg RMS:', avgRMS.toFixed(4), `(need at least ${(effectiveMinRatio * 100).toFixed(0)}% confirmed human speech)`);
                    this.isProcessingAudio = false;
                    this.isWaitingForResponse = false;
                    this.voiceDetected = false;
                    this.audioBuffer = [];
                    this.hideLoading();
                    this.hideListeningMessage();
                    // Don't restart immediately - let silence timer handle it to avoid loops
                    if (this.isRecording && this.silenceTimer) {
                        // Timer is already running, just clear buffer and let it continue
                    } else if (this.isRecording) {
                        // Start a new timer after a short delay
                        setTimeout(() => {
                            if (this.isRecording && !this.isProcessingAudio) {
                                this.startSilenceTimer();
                            }
                        }, 500);
                    }
                    return;
                }

                // Final RMS check - only reject if RMS is very low (likely silence)
                const minRMS = 0.01; // Very lenient - only reject near-silence

                if (avgRMS < minRMS) {
                    console.warn('⚠️ Audio RMS too low (near silence):', avgRMS.toFixed(4), `(need at least ${minRMS.toFixed(3)})`);
                    this.isProcessingAudio = false;
                    this.isWaitingForResponse = false;
                    this.voiceDetected = false;
                    this.audioBuffer = [];
                    this.hideLoading();
                    this.hideListeningMessage();
                    // Don't restart immediately - let silence timer handle it to avoid loops
                    if (this.isRecording && this.silenceTimer) {
                        // Timer is already running, just clear buffer and let it continue
                    } else if (this.isRecording) {
                        // Start a new timer after a short delay
                        setTimeout(() => {
                            if (this.isRecording && !this.isProcessingAudio) {
                                this.startSilenceTimer();
                            }
                        }, 500);
                    }
                    return;
                }

                console.log('✅ Speech validation passed - Speech ratio:', speechRatio.toFixed(2), 'Voice energy ratio:', voiceEnergyRatio.toFixed(2), 'Avg RMS:', avgRMS.toFixed(4));

                console.log('✅ Audio validation passed - Speech ratio:', speechRatio.toFixed(2), 'Duration:', duration.toFixed(2), 's');

                // Convert to WAV
                const wavBuffer = this.float32ArrayToWav(combinedBuffer, sampleRate);
                const audioBlob = new Blob([wavBuffer], { type: 'audio/wav' });

                console.log('📤 Created WAV blob, size:', audioBlob.size, 'bytes, duration:', duration.toFixed(2), 's');

                // Validate blob size - need at least 5KB of audio
                if (audioBlob.size < 5000) {
                    console.warn('⚠️ Audio blob too small:', audioBlob.size, 'bytes (need at least 5KB)');
                    this.isProcessingAudio = false;
                    this.isWaitingForResponse = false; // Reset waiting flag so recording can restart
                    this.voiceDetected = false;
                    this.audioBuffer = [];
                    // Hide messages
                    this.hideLoading();
                    this.hideListeningMessage();
                    // Restart recording immediately
                    if (this.isRecording) {
                        this.restartRecording();
                    }
                    return;
                }

                console.log('✅ WAV blob ready to send');

                // Send via WebSocket if available, otherwise HTTP fallback
                if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                    console.log('📡 Sending audio via WebSocket, size:', audioBlob.size, 'bytes');
                    this.websocket.send(audioBlob);
                } else {
                    // HTTP fallback
                    await this.sendAudioViaHTTP(audioBlob);
                }

                // Clear buffer after sending - we'll collect new ones if user interrupts
                this.audioBuffer = [];

            } catch (error) {
                console.error('Error processing audio:', error);
                this.isProcessingAudio = false;
                this.isWaitingForResponse = false; // Reset waiting flag so recording can restart
                // Hide messages
                this.hideLoading();
                this.hideListeningMessage();
                // Restart recording on error
                if (this.isRecording) {
                    this.restartRecording();
                }
            }
        }

        async sendAudioViaHTTP(audioBlob) {
            try {
                const formData = new FormData();
                formData.append('audio', audioBlob, 'audio.wav');
                formData.append('session_id', this.sessionId);

                const response = await fetch(`${this.apiUrl}/api/voice`, {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                this.handleVoiceResponse(data);

            } catch (error) {
                console.error('Error sending audio via HTTP:', error);
                this.isProcessingAudio = false;
                this.isWaitingForResponse = false;
                // Hide messages
                this.hideLoading();
                this.hideListeningMessage();
                // Restart recording on error
                if (this.isRecording) {
                    this.restartRecording();
                }
            }
        }

        cancelProcessing() {
            console.log('🛑 Cancelling ongoing audio processing due to user interruption');

            // Stop current TTS audio playback immediately
            if (this.currentAudio) {
                this.currentAudio.pause();
                this.currentAudio.currentTime = 0; // Reset to beginning
                this.currentAudio = null;
            }

            // Mark TTS as not playing so we can start collecting audio
            this.isPlayingTTS = false;

            // Cancel any pending processing
            this.isProcessingAudio = false;
            this.isWaitingForResponse = false;
            this.isPlayingTTS = false; // TTS is no longer playing

            // Don't clear voiceDetected if we just interrupted - we want to keep collecting
            // Only clear if we're not in the middle of an interruption
            if (!this.voiceDetected) {
                this.audioBuffer = [];
            }
            // voiceDetected stays true if we interrupted, so we continue collecting

            // Restart silence timer if still recording
            if (this.isRecording && this.audioContext && this.audioContext.state === 'running') {
                // Small delay to ensure audio processing resumes
                setTimeout(() => {
                    this.startSilenceTimer();
                    console.log('🔄 Recording restarted after interruption - ready for user input');
                }, 100);
            }
        }

        async connectWebSocket() {
            if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                return;
            }

            return new Promise((resolve, reject) => {
                const wsUrl = this.apiUrl.replace('http://', 'ws://').replace('https://', 'wss://') + '/ws/voice';
                console.log('🔌 Connecting to WebSocket:', wsUrl);
                console.log('   API URL:', this.apiUrl);

                this.websocket = new WebSocket(wsUrl);

                const timeout = setTimeout(() => {
                    if (this.websocket.readyState !== WebSocket.OPEN) {
                        this.websocket.close();
                        console.log('❌ WebSocket connection timeout after 10 seconds');
                        reject(new Error('WebSocket connection timeout'));
                    }
                }, 10000);

                this.websocket.onopen = () => {
                    console.log('✅ WebSocket connected');
                };

                this.websocket.onmessage = async (event) => {
                    if (event.data instanceof Blob) {
                        // Binary audio data (TTS response)
                        const audioUrl = URL.createObjectURL(event.data);
                        // playAudio() will set isPlayingTTS flag to prevent listening to own voice
                        await this.playAudio(audioUrl);
                    } else {
                        // JSON message
                        try {
                            const data = JSON.parse(event.data);

                            if (data.type === 'connected') {
                                clearTimeout(timeout);
                                resolve();
                            } else if (data.type === 'ready') {
                                // Send init message
                                this.websocket.send(JSON.stringify({
                                    type: 'init',
                                    session_id: this.sessionId
                                }));
                            } else if (data.type === 'answer') {
                                this.handleVoiceResponse(data);
                            } else if (data.type === 'error') {
                                console.error('WebSocket error:', data.message);
                                this.isProcessingAudio = false;
                                this.isWaitingForResponse = false;
                                // Hide messages
                                this.hideLoading();
                                this.hideListeningMessage();
                                // Restart recording on error
                                if (this.isRecording) {
                                    this.restartRecording();
                                }
                            } else if (data.type === 'status') {
                                console.log('Status:', data.message);
                            }
                        } catch (e) {
                            console.error('Error parsing WebSocket message:', e);
                        }
                    }
                };

                this.websocket.onerror = (error) => {
                    console.error('❌ WebSocket error:', error);
                    console.error('   Error details:', wsUrl);
                    clearTimeout(timeout);
                    reject(error);
                };

                this.websocket.onclose = () => {
                    console.log('🔌 WebSocket closed');
                    this.websocket = null;
                };
            });
        }

        handleVoiceResponse(data) {
            this.isProcessingAudio = false;
            this.isWaitingForResponse = false; // Response received, no longer waiting

            // Hide thinking message
            this.hideLoading();
            this.hideListeningMessage();

            // Clear audio buffer after successful processing
            this.audioBuffer = [];

            // Display user's question if provided
            if (data.question) {
                this.addMessage('user', data.question);
            }

            // Display assistant's response
            if (data.text) {
                this.addMessage('assistant', data.text);
            }

            if (data.audio) {
                // Decode base64 audio (now using wav format from Groq)
                const audioBytes = Uint8Array.from(atob(data.audio), c => c.charCodeAt(0));
                const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
                const audioUrl = URL.createObjectURL(audioBlob);

                // Play audio and then restart recording
                // Note: playAudio() sets isPlayingTTS flag to prevent listening to own voice
                this.playAudio(audioUrl).then(() => {
                    // After audio finishes, restart recording if still in recording mode
                    if (this.isRecording && !this.isWaitingForResponse && !this.isPlayingTTS) {
                        console.log('✅ TTS finished, restarting recording for next question');
                        this.restartRecording();
                    }
                }).catch(() => {
                    // Even if audio fails, restart recording
                    if (this.isRecording && !this.isWaitingForResponse) {
                        console.log('✅ Response finished (with error), restarting recording');
                        this.restartRecording();
                    }
                });
            } else {
                // If no audio, restart recording immediately
                if (this.isRecording && !this.isWaitingForResponse && !this.isPlayingTTS) {
                    console.log('✅ Response received (no audio), restarting recording');
                    this.restartRecording();
                }
            }
        }

        async playAudio(audioUrl) {
            return new Promise((resolve, reject) => {
                // Mark that TTS is playing - microphone stays connected but won't collect audio
                this.isPlayingTTS = true;
                console.log('🔊 Starting TTS playback - microphone stays connected for interruption detection');

                // Clear any audio buffer that might have been collected
                // We don't disconnect - microphone stays connected to detect user interruptions
                this.audioBuffer = [];
                this.voiceDetected = false;

                const audio = new Audio(audioUrl);
                this.currentAudio = audio;

                // Handle user interruption during playback
                audio.addEventListener('pause', () => {
                    if (this.isPlayingTTS && this.currentAudio && this.currentAudio.paused) {
                        console.log('🛑 TTS playback paused by user interruption');
                        this.isPlayingTTS = false;
                    }
                });

                audio.onended = () => {
                    URL.revokeObjectURL(audioUrl);
                    this.currentAudio = null;
                    this.isPlayingTTS = false; // TTS finished playing
                    console.log('✅ TTS playback finished - microphone ready for next question');
                    resolve();
                };

                audio.onerror = (error) => {
                    console.error('Error playing audio:', error);
                    URL.revokeObjectURL(audioUrl);
                    this.currentAudio = null;
                    this.isPlayingTTS = false; // TTS error, mark as not playing
                    reject(error);
                };

                audio.play().catch(error => {
                    console.error('Error starting audio playback:', error);
                    this.isPlayingTTS = false; // Failed to play, mark as not playing
                    reject(error);
                });
            });
        }
    }

    // Auto-initialize when DOM is ready
    function initWidget() {
        try {
            console.log('🚀 Starting chatbot widget initialization...');
            console.log('Document ready state:', document.readyState);
            console.log('Document body exists:', !!document.body);

            // Get configuration from script tag or data attributes
            const script = document.currentScript ||
                document.querySelector('script[src*="chatbot-widget.js"]');

            console.log('Script element found:', !!script);
            if (script) {
                console.log('Script dataset:', script.dataset);
                console.log('Script src:', script.src);
            }

            const config = {
                apiUrl: script?.dataset?.apiUrl || null,
                theme: script?.dataset?.theme || 'light',
                position: script?.dataset?.position || 'bottom-right',
                primaryColor: script?.dataset?.primaryColor || '#007bff',
            };

            // Initialize widget
            console.log('Initializing chatbot widget with config:', config);
            window.chatbotWidget = new ChatbotWidget(config);
            console.log('Chatbot widget initialized successfully', window.chatbotWidget);

            // Verify widget is in DOM
            setTimeout(() => {
                const widgetElement = document.getElementById('chatbot-widget');
                if (widgetElement) {
                    console.log('✅ Widget element found in DOM:', widgetElement);
                    const styles = window.getComputedStyle(widgetElement);
                    console.log('Widget position:', styles.position);
                    console.log('Widget display:', styles.display);
                    console.log('Widget visibility:', styles.visibility);
                    console.log('Widget z-index:', styles.zIndex);
                    console.log('Widget bottom:', styles.bottom);
                    console.log('Widget right:', styles.right);
                    console.log('Widget classes:', widgetElement.className);

                    const toggleButton = document.getElementById('chatbot-toggle');
                    if (toggleButton) {
                        const toggleStyles = window.getComputedStyle(toggleButton);
                        console.log('✅ Toggle button found');
                        console.log('Toggle display:', toggleStyles.display);
                        console.log('Toggle visibility:', toggleStyles.visibility);
                        console.log('Toggle width:', toggleStyles.width);
                        console.log('Toggle height:', toggleStyles.height);
                    } else {
                        console.error('❌ Toggle button NOT found!');
                    }
                } else {
                    console.error('❌ Widget element NOT found in DOM!');
                }
            }, 100);
        } catch (error) {
            console.error('❌ Error initializing chatbot widget:', error);
            console.error('Error stack:', error.stack);
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        console.log('Document is loading, waiting for DOMContentLoaded...');
        document.addEventListener('DOMContentLoaded', initWidget);
    } else {
        console.log('Document already ready, initializing immediately...');
        initWidget();
    }

})();
