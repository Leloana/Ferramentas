import { myRole } from './config.js';

export async function getMicrophoneStream() {
    const isMobileMic = (myRole === 'mic');
    if (isMobileMic) {
        console.log("🎤 [Celular como Mic] Forçando a desativação de echoCancellation, noiseSuppression e autoGainControl para alta fidelidade vocal.");
    }

    const constraintsList = [
        { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } },
        { audio: { echoCancellation: { ideal: false }, noiseSuppression: { ideal: false }, autoGainControl: { ideal: false }, channelCount: { ideal: 1 } } },
        { audio: true }
    ];

    let lastErr = null;
    for (const constraints of constraintsList) {
        try {
            console.log("Tentando obter microfone com constraints:", constraints);
            const stream = await navigator.mediaDevices.getUserMedia(constraints);

            if (isMobileMic && stream) {
                stream.getAudioTracks().forEach(track => {
                    const settings = typeof track.getSettings === 'function' ? track.getSettings() : {};
                    console.log("Configurações atuais do microfone do celular:", settings);
                    if (typeof track.applyConstraints === 'function') {
                        track.applyConstraints({
                            echoCancellation: false,
                            noiseSuppression: false,
                            autoGainControl: false
                        }).then(() => {
                            console.log("Restrições acústicas de voz aplicadas diretamente na track com sucesso!");
                        }).catch(err => {
                            console.warn("Não foi possível aplicar restrições adicionais na track:", err);
                        });
                    }
                });
            }

            console.log("Microfone obtido com sucesso!");
            return stream;
        } catch (err) {
            console.warn("Falha ao obter microfone com constraints:", constraints, err);
            lastErr = err;
        }
    }
    throw lastErr;
}
