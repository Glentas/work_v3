/* AudioWorklet-процессор для записи микрофона.
 * Надёжнее устаревшего ScriptProcessorNode в Firefox/LibreWolf.
 * Пересылает блоки отсчётов (Float32) в основной поток через port.
 */
class RecorderProcessor extends AudioWorkletProcessor {
    process(inputs) {
        const input = inputs[0];
        if (input && input.length > 0 && input[0].length > 0) {
            // копируем, т.к. входной буфер переиспользуется движком
            this.port.postMessage(new Float32Array(input[0]));
        }
        return true; // держать процессор живым
    }
}

registerProcessor("recorder-processor", RecorderProcessor);
