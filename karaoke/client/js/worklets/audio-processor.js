// Captura do microfone → PCM Int16 mono a 16 kHz, em pacotes de 100 ms.
// Formato (espelha server/mic_stream.py): "KM01" + índice da 1ª amostra
// (float64 LE) + taxa (uint32 LE) + amostras Int16 LE.
// O índice conta TODAS as amostras desde o início da captura, mesmo as que o
// app não envia (fora do verso) — é o que o servidor usa para ancorar o tempo.
const TARGET_RATE = 16000;
const CHUNK_SAMPLES = 1600;
const HEADER_BYTES = 16;
const CUTOFF_HZ = 7000;

// Biquad passa-baixa (RBJ cookbook). Dois em série com esses Q formam um
// Butterworth de 4ª ordem: tira o que aliasaria acima de 8 kHz.
function lowpassBiquad(cutoff, fs, q) {
    const w0 = 2 * Math.PI * cutoff / fs;
    const alpha = Math.sin(w0) / (2 * q);
    const cos = Math.cos(w0);
    const a0 = 1 + alpha;
    return {
        b0: (1 - cos) / 2 / a0,
        b1: (1 - cos) / a0,
        b2: (1 - cos) / 2 / a0,
        a1: -2 * cos / a0,
        a2: (1 - alpha) / a0,
        x1: 0, x2: 0, y1: 0, y2: 0,
    };
}

function runBiquad(f, x) {
    const y = f.b0 * x + f.b1 * f.x1 + f.b2 * f.x2 - f.a1 * f.y1 - f.a2 * f.y2;
    f.x2 = f.x1; f.x1 = x;
    f.y2 = f.y1; f.y1 = y;
    return y;
}

class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        // `sampleRate` é global no AudioWorkletGlobalScope (48 kHz, 44,1 kHz no iPhone...).
        this.step = sampleRate / TARGET_RATE;
        this.filters = sampleRate > 2 * CUTOFF_HZ
            ? [lowpassBiquad(CUTOFF_HZ, sampleRate, 0.5412), lowpassBiquad(CUTOFF_HZ, sampleRate, 1.3066)]
            : [];
        this.inIndex = 0;      // índice da próxima amostra de entrada
        this.nextOut = 0;      // posição (em amostras de entrada) da próxima saída
        this.prev = 0;         // última amostra de entrada filtrada
        this.outIndex = 0;     // amostras de saída produzidas desde o início
        this.chunk = new Int16Array(CHUNK_SAMPLES);
        this.fill = 0;
    }

    push(value) {
        const clamped = Math.max(-1, Math.min(1, value));
        this.chunk[this.fill++] = clamped < 0 ? clamped * 32768 : clamped * 32767;
        this.outIndex++;
        if (this.fill === CHUNK_SAMPLES) {
            const packet = new ArrayBuffer(HEADER_BYTES + CHUNK_SAMPLES * 2);
            const view = new DataView(packet);
            view.setUint8(0, 0x4b); view.setUint8(1, 0x4d); view.setUint8(2, 0x30); view.setUint8(3, 0x31); // "KM01"
            view.setFloat64(4, this.outIndex - CHUNK_SAMPLES, true);
            view.setUint32(12, TARGET_RATE, true);
            new Int16Array(packet, HEADER_BYTES).set(this.chunk);
            this.port.postMessage(packet, [packet]);
            this.fill = 0;
        }
    }

    process(inputs) {
        const input = inputs[0];
        if (input.length > 0) {
            const samples = input[0];
            for (let i = 0; i < samples.length; i++) {
                let y = samples[i];
                for (const f of this.filters) y = runBiquad(f, y);
                // Interpolação linear entre a amostra anterior (inIndex - 1) e a atual.
                while (this.nextOut <= this.inIndex) {
                    const frac = this.nextOut - (this.inIndex - 1);
                    this.push(this.prev + (y - this.prev) * frac);
                    this.nextOut += this.step;
                }
                this.prev = y;
                this.inIndex++;
            }
        }
        return true;
    }
}
registerProcessor('audio-processor', AudioProcessor);
