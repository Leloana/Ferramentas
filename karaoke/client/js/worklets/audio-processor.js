class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 4096;
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;
    }
    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input.length > 0) {
            const samples = input[0];
            for (let i = 0; i < samples.length; i++) {
                this.buffer[this.bufferIndex++] = samples[i];
                if (this.bufferIndex >= this.bufferSize) {
                    const chunk = this.buffer.slice(0);
                    this.port.postMessage(chunk.buffer, [chunk.buffer]);
                    this.bufferIndex = 0;
                }
            }
        }
        return true;
    }
}
registerProcessor('audio-processor', AudioProcessor);
