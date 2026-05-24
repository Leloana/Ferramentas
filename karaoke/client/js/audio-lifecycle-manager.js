import { Jungle, getMultiplier } from './jungle.js';

/**
 * Microphone audio constraints configuration.
 * Configured for maximum vocal fidelity on resource-constrained devices
 * by disabling default echo cancellation, noise suppression, and auto gain control.
 *
 * @type {MediaTrackConstraints}
 */
const MIC_CONSTRAINTS_CONFIG = {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
    channelCount: 1
};

/**
 * Global registry to track loaded worklets per AudioContext instance.
 * Prevents double-registration errors in the Web Audio API.
 * 
 * @type {WeakMap<AudioContext, Promise<void>>}
 */
const loadedWorklets = new WeakMap();

/**
 * Manages the lifecycle of AudioContext, microphone stream capture,
 * worklet injection, and playback pitch-shifting audio graphs.
 * Optimized for iOS Safari and Android Chrome compatibility.
 */
export class AudioLifecycleManager {
    /**
     * @param {Object} [options]
     * @param {boolean} [options.captureMic=false] - Whether to capture and process microphone input.
     * @param {HTMLMediaElement} [options.mediaElement=null] - Optional HTML media element to connect for playback and pitch shifting.
     * @param {function(ArrayBuffer): void} [options.onAudioChunk=null] - Callback invoked when a new audio worklet chunk is captured.
     */
    constructor(options = {}) {
        this.captureMic = options.captureMic || false;
        this.mediaElement = options.mediaElement || null;
        this.onAudioChunk = options.onAudioChunk || null;

        /** @type {AudioContext|null} */
        this.audioContext = null;
        /** @type {MediaStream|null} */
        this.localStream = null;
        /** @type {MediaStreamAudioSourceNode|null} */
        this.micSourceNode = null;
        /** @type {AudioWorkletNode|null} */
        this.micProcessorNode = null;
        /** @type {AnalyserNode|null} */
        this.analyserNode = null;
        /** @type {MediaElementAudioSourceNode|null} */
        this.mediaElementSource = null;
        /** @type {Jungle|null} */
        this.jungleNode = null;
        /** @type {number} */
        this.currentTranspose = 0;

        /**
         * Track all Web Audio nodes for explicit disconnection on cleanup.
         * @type {Set<AudioNode>}
         */
        this.nodes = new Set();

        /**
         * Track iOS user gesture event listener binding.
         * @type {function(): Promise<void>|null}
         * @private
         */
        this._iosResumeBound = null;

        /** @type {boolean} */
        this._initialized = false;
        /** @type {boolean} */
        this._started = false;
    }

    /**
     * Initializes the AudioContext, sets up iOS Safari user-gesture resumption handlers,
     * and pre-registers the audio worklet module if mic capture is enabled.
     * 
     * @returns {Promise<void>} Resolves when initialization is complete.
     */
    async init() {
        if (this._initialized) {
            console.warn("AudioLifecycleManager: Already initialized.");
            return;
        }

        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            throw new Error("Web Audio API is not supported in this browser.");
        }

        this.audioContext = new AudioContextClass();
        console.log("AudioLifecycleManager: AudioContext created with sampleRate =", this.audioContext.sampleRate);

        // Setup iOS Safari suspended-on-load workaround
        if (this.audioContext.state === 'suspended') {
            this._setupIOSResumeHandler();
        }

        // Register worklet module if mic capture is required
        if (this.captureMic) {
            await this._ensureWorkletRegistered(this.audioContext);
        }

        this._initialized = true;
    }

    /**
     * Starts audio processing: captures microphone stream, sets up the audio worklet node,
     * connects the playback media element source node, and builds the routing graph.
     * 
     * @returns {Promise<void>} Resolves when audio graph has started.
     */
    async start() {
        if (!this._initialized) {
            await this.init();
        }

        if (this._started) {
            console.warn("AudioLifecycleManager: Already started.");
            return;
        }

        // Ensure context is running (especially important inside iOS click/gesture context)
        if (this.audioContext.state === 'suspended') {
            try {
                await this.audioContext.resume();
                console.log("AudioLifecycleManager: AudioContext resumed successfully during start.");
                this._cleanupIOSResumeHandler();
            } catch (err) {
                console.warn("AudioLifecycleManager: Failed to resume AudioContext during start. Waiting for user gesture.", err);
            }
        }

        // 1. Microphone setup
        if (this.captureMic && !this.localStream) {
            try {
                this.localStream = await this._getMicStream();
                this.micSourceNode = this.audioContext.createMediaStreamSource(this.localStream);
                this.nodes.add(this.micSourceNode);

                // Setup analyser for visualization (e.g. VU meters)
                this.analyserNode = this.audioContext.createAnalyser();
                this.analyserNode.fftSize = 256;
                this.nodes.add(this.analyserNode);
                this.micSourceNode.connect(this.analyserNode);

                // Create worklet node
                this.micProcessorNode = new AudioWorkletNode(this.audioContext, 'audio-processor');
                this.nodes.add(this.micProcessorNode);

                if (this.onAudioChunk) {
                    this.micProcessorNode.port.onmessage = (event) => {
                        this.onAudioChunk(event.data);
                    };
                }

                this.micSourceNode.connect(this.micProcessorNode);
                this.micProcessorNode.connect(this.audioContext.destination);
            } catch (err) {
                console.error("AudioLifecycleManager: Failed to initialize microphone capture graph:", err);
                throw err;
            }
        }

        // 2. Playback/media element setup
        if (this.mediaElement && !this.mediaElementSource) {
            try {
                this.mediaElementSource = this.audioContext.createMediaElementSource(this.mediaElement);
                this.nodes.add(this.mediaElementSource);
                this.updateTranspose(this.currentTranspose);
            } catch (err) {
                console.error("AudioLifecycleManager: Failed to capture MediaElement:", err);
                throw err;
            }
        }

        this._started = true;
    }

    /**
     * Suspends the AudioContext to temporarily stop processing audio and conserve CPU/battery.
     * 
     * @returns {Promise<void>} Resolves when the context has suspended.
     */
    async stop() {
        if (this.audioContext && this.audioContext.state === 'running') {
            await this.audioContext.suspend();
            console.log("AudioLifecycleManager: AudioContext suspended.");
        }
    }

    /**
     * Completely cleans up all audio resources: closes the AudioContext, stops all
     * active BufferSourceNodes, disconnects all nodes, stops microphone tracks, and nulls references.
     * Clones the HTMLMediaElement to clear Web Audio node bindings and prevent InvalidStateError on reuse.
     * 
     * @returns {Promise<void>} Resolves when cleanup is complete.
     */
    async destroy() {
        console.log("AudioLifecycleManager: Destroying audio resources...");

        this._cleanupIOSResumeHandler();

        // 1. Stop all tracks in the microphone media stream
        if (this.localStream) {
            try {
                this.localStream.getTracks().forEach(track => {
                    track.stop();
                    console.log("AudioLifecycleManager: Stream track stopped:", track.label);
                });
            } catch (e) {
                console.warn("AudioLifecycleManager: Error stopping stream tracks:", e);
            }
            this.localStream = null;
        }

        // 2. Stop any BufferSourceNodes (e.g. from Jungle pitch shifter)
        this._stopJungleBufferSources();

        // 3. Disconnect all tracked AudioNodes
        for (const node of this.nodes) {
            try {
                node.disconnect();
            } catch (e) {
                // Ignore errors from nodes already disconnected
            }
        }
        this.nodes.clear();

        // Null all node references
        this.micSourceNode = null;
        if (this.micProcessorNode) {
            this.micProcessorNode.port.onmessage = null;
            this.micProcessorNode = null;
        }
        this.analyserNode = null;
        this.mediaElementSource = null;

        // 4. Safely close AudioContext
        if (this.audioContext) {
            try {
                if (this.audioContext.state !== 'closed') {
                    await this.audioContext.close();
                    console.log("AudioLifecycleManager: AudioContext closed.");
                }
            } catch (e) {
                console.error("AudioLifecycleManager: Error closing AudioContext:", e);
            }
            this.audioContext = null;
        }

        // 5. Clone and replace media element to reset browser audio graph binding
        if (this.mediaElement) {
            try {
                const oldPlayer = this.mediaElement;
                const newPlayer = oldPlayer.cloneNode(true);
                
                // Copy runtime-assigned listeners and state
                newPlayer.onended = oldPlayer.onended;
                newPlayer.onplay = oldPlayer.onplay;
                newPlayer.onpause = oldPlayer.onpause;
                
                if (oldPlayer.parentNode) {
                    oldPlayer.parentNode.replaceChild(newPlayer, oldPlayer);
                    console.log("AudioLifecycleManager: HTMLMediaElement cloned and replaced to reset bindings.");
                }
            } catch (e) {
                console.error("AudioLifecycleManager: Error cloning media element:", e);
            }
            this.mediaElement = null;
        }

        this._initialized = false;
        this._started = false;
    }

    /**
     * Updates the pitch shift offset (transpose) by recreating or routing through the Jungle node.
     * 
     * @param {number} transpose - The pitch transposition offset in semitones (-6 to 6).
     */
    updateTranspose(transpose) {
        this.currentTranspose = transpose;
        if (!this.audioContext || !this.mediaElementSource) return;

        // Disconnect media source
        try {
            this.mediaElementSource.disconnect();
        } catch (e) {
            console.warn("AudioLifecycleManager: Error disconnecting mediaElementSource:", e);
        }

        // Clean up previous Jungle node
        this._stopJungleBufferSources();

        // Route media element source through Jungle or directly to destination
        if (transpose === 0) {
            this.mediaElementSource.connect(this.audioContext.destination);
            console.log("AudioLifecycleManager: Connected playback directly to destination (transpose=0).");
        } else {
            this.jungleNode = new Jungle(this.audioContext);
            this.jungleNode.setPitchOffset(getMultiplier(transpose));
            
            this.mediaElementSource.connect(this.jungleNode.input);
            this.jungleNode.output.connect(this.audioContext.destination);
            console.log(`AudioLifecycleManager: Connected playback via Jungle node (transpose=${transpose}).`);
        }
    }

    /**
     * Gets the analyser node for microphone level/VU visualization.
     * 
     * @returns {AnalyserNode|null} The current AnalyserNode instance.
     */
    getAnalyser() {
        return this.analyserNode;
    }

    /**
     * Obtains the microphone stream using robust fallback constraints.
     * 
     * @returns {Promise<MediaStream>} Resolves to the microphone MediaStream.
     * @private
     */
    async _getMicStream() {
        const constraintsList = [
            {
                audio: {
                    echoCancellation: MIC_CONSTRAINTS_CONFIG.echoCancellation,
                    noiseSuppression: MIC_CONSTRAINTS_CONFIG.noiseSuppression,
                    autoGainControl: MIC_CONSTRAINTS_CONFIG.autoGainControl,
                    channelCount: MIC_CONSTRAINTS_CONFIG.channelCount
                }
            },
            {
                audio: {
                    echoCancellation: { ideal: MIC_CONSTRAINTS_CONFIG.echoCancellation },
                    noiseSuppression: { ideal: MIC_CONSTRAINTS_CONFIG.noiseSuppression },
                    autoGainControl: { ideal: MIC_CONSTRAINTS_CONFIG.autoGainControl },
                    channelCount: { ideal: MIC_CONSTRAINTS_CONFIG.channelCount }
                }
            },
            { audio: true }
        ];

        let lastErr = null;
        for (const constraints of constraintsList) {
            try {
                console.log("AudioLifecycleManager: Requesting microphone with constraints:", constraints);
                const stream = await navigator.mediaDevices.getUserMedia(constraints);
                
                if (stream) {
                    stream.getAudioTracks().forEach(track => {
                        if (typeof track.applyConstraints === 'function') {
                            track.applyConstraints({
                                echoCancellation: MIC_CONSTRAINTS_CONFIG.echoCancellation,
                                noiseSuppression: MIC_CONSTRAINTS_CONFIG.noiseSuppression,
                                autoGainControl: MIC_CONSTRAINTS_CONFIG.autoGainControl
                            }).catch(err => {
                                console.warn("AudioLifecycleManager: Failed to apply constraints on track:", err);
                            });
                        }
                    });
                }
                console.log("AudioLifecycleManager: Microphone captured successfully!");
                return stream;
            } catch (err) {
                console.warn("AudioLifecycleManager: Failed microphone constraints:", constraints, err);
                lastErr = err;
            }
        }
        throw lastErr;
    }

    /**
     * Guards worklet loading to prevent double-registration on the same AudioContext.
     * 
     * @param {AudioContext} audioCtx - The target AudioContext.
     * @returns {Promise<void>} Resolves when registration check/loading is done.
     * @private
     */
    async _ensureWorkletRegistered(audioCtx) {
        if (!loadedWorklets.has(audioCtx)) {
            const loadPromise = audioCtx.audioWorklet.addModule('/js/worklets/audio-processor.js')
                .then(() => {
                    console.log("AudioLifecycleManager: Audio worklet processor registered successfully.");
                })
                .catch(err => {
                    loadedWorklets.delete(audioCtx); // Clear from registry so load can be retried
                    throw err;
                });
            loadedWorklets.set(audioCtx, loadPromise);
        }
        return loadedWorklets.get(audioCtx);
    }

    /**
     * Sets up user gesture event listeners on the window to resume AudioContext (specifically for iOS Safari).
     * 
     * @private
     */
    _setupIOSResumeHandler() {
        this._iosResumeBound = async () => {
            if (this.audioContext && this.audioContext.state === 'suspended') {
                try {
                    await this.audioContext.resume();
                    console.log("AudioLifecycleManager: AudioContext resumed via user gesture.");
                    this._cleanupIOSResumeHandler();
                } catch (err) {
                    console.warn("AudioLifecycleManager: Failed to resume AudioContext on gesture:", err);
                }
            } else if (!this.audioContext || this.audioContext.state === 'running') {
                this._cleanupIOSResumeHandler();
            }
        };

        window.addEventListener('click', this._iosResumeBound, true);
        window.addEventListener('touchstart', this._iosResumeBound, true);
        window.addEventListener('keydown', this._iosResumeBound, true);
    }

    /**
     * Removes the iOS user gesture event listeners.
     * 
     * @private
     */
    _cleanupIOSResumeHandler() {
        if (this._iosResumeBound) {
            window.removeEventListener('click', this._iosResumeBound, true);
            window.removeEventListener('touchstart', this._iosResumeBound, true);
            window.removeEventListener('keydown', this._iosResumeBound, true);
            this._iosResumeBound = null;
        }
    }

    /**
     * Safely stops and disconnects all internal AudioBufferSourceNodes inside the Jungle pitch-shifter.
     * 
     * @private
     */
    _stopJungleBufferSources() {
        if (this.jungleNode) {
            try {
                const bufferNodes = [
                    this.jungleNode.mod1,
                    this.jungleNode.mod2,
                    this.jungleNode.mod3,
                    this.jungleNode.mod4,
                    this.jungleNode.fade1,
                    this.jungleNode.fade2
                ];
                bufferNodes.forEach(node => {
                    if (node) {
                        try { node.stop(); } catch (e) {}
                        try { node.disconnect(); } catch (e) {}
                    }
                });
                this.jungleNode.output.disconnect();
            } catch (e) {
                console.warn("AudioLifecycleManager: Error disconnecting jungleNode internal sources:", e);
            }
            this.jungleNode = null;
        }
    }
}
