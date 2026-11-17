"use strict";


/*
============================================================
 KASF Generator v1
============================================================

・ブラウザのみで動作
・外部ライブラリなし
・WAV / MP3 等 → AudioBuffer
・マイク録音
・FFT
・Periodic Hann
・50% overlap
・KASF v1生成
・48bit Component packing

============================================================
*/


const $ = id => document.getElementById(id);


const state = {

    audioBuffer: null,

    sourceName: "",

    blob: null,

    recorder: null,

    chunks: []

};



/*
============================================================
 Utility
============================================================
*/


function log(message, replace = false) {

    const element = $("log");

    if (replace) {

        element.textContent = message;

    } else {

        element.textContent +=
            (element.textContent ? "\n" : "") +
            message;

    }

    element.scrollTop =
        element.scrollHeight;

}



function setProgress(value) {

    $("progress").value =
        Math.max(
            0,
            Math.min(1, value)
        );

}



/*
============================================================
 KASF uint64
============================================================
*/


function writeU64(view, offset, value) {

    view.setBigUint64(
        offset,
        BigInt(value),
        true
    );

}



/*
============================================================
 KASF 48bit Component

 bits 0-23   Frequency
 bits 24-37  Amplitude
 bits 38-47  Phase
============================================================
*/


function packComponent(
    frequency,
    amplitude,
    phase
) {

    /*
    Frequency
    0 - 96000 Hz
    */

    const f =
        Math.max(
            0,
            Math.min(96000, frequency)
        );


    /*
    Amplitude
    0 - 1
    */

    const a =
        Math.max(
            0,
            Math.min(1, amplitude)
        );


    /*
    Phase
    0 - 2π
    */

    let p =
        phase % (2 * Math.PI);

    if (p < 0) {
        p += 2 * Math.PI;
    }


    /*
    Quantization
    */

    const frequencyQ =
        Math.round(
            f / 96000 * 0xFFFFFF
        );


    const amplitudeQ =
        Math.round(
            a * 16383
        );


    const phaseQ =
        Math.round(
            p / (2 * Math.PI) * 1024
        ) & 1023;


    /*
    Pack

        frequency
        amplitude
        phase
    */

    const value =
        BigInt(frequencyQ)
        |
        (BigInt(amplitudeQ) << 24n)
        |
        (BigInt(phaseQ) << 38n);


    const output =
        new Uint8Array(6);


    for (let i = 0; i < 6; i++) {

        output[i] =
            Number(
                (value >> BigInt(i * 8))
                & 255n
            );

    }


    return output;

}



/*
============================================================
 FFT
============================================================
*/


function fft(real, imag) {

    const n = real.length;


    /*
    Bit reversal
    */

    for (
        let i = 1, j = 0;
        i < n;
        i++
    ) {

        let bit = n >> 1;

        for (; j & bit; bit >>= 1) {
            j ^= bit;
        }

        j ^= bit;


        if (i < j) {

            let temp =
                real[i];

            real[i] =
                real[j];

            real[j] =
                temp;


            temp =
                imag[i];

            imag[i] =
                imag[j];

            imag[j] =
                temp;

        }

    }


    /*
    Butterfly
    */

    for (
        let length = 2;
        length <= n;
        length <<= 1
    ) {

        const angle =
            2 * Math.PI / length;


        const cos =
            Math.cos(angle);

        const sin =
            Math.sin(angle);


        for (
            let start = 0;
            start < n;
            start += length
        ) {

            let wr = 1;
            let wi = 0;


            const half =
                length >> 1;


            for (
                let j = 0;
                j < half;
                j++
            ) {

                const ur =
                    real[start + j];

                const ui =
                    imag[start + j];


                const vr =
                    real[start + j + half] * wr
                    -
                    imag[start + j + half] * wi;


                const vi =
                    real[start + j + half] * wi
                    +
                    imag[start + j + half] * wr;


                real[start + j] =
                    ur + vr;

                imag[start + j] =
                    ui + vi;


                real[start + j + half] =
                    ur - vr;

                imag[start + j + half] =
                    ui - vi;


                const nextWr =
                    wr * cos -
                    wi * sin;


                wi =
                    wr * sin +
                    wi * cos;


                wr =
                    nextWr;

            }

        }

    }

}



/*
============================================================
 Resampling
============================================================
*/


async function resampleBuffer(
    source,
    targetRate
) {

    if (
        source.sampleRate ===
        targetRate
    ) {

        return source;

    }


    const newLength =
        Math.max(
            1,
            Math.round(
                source.length *
                targetRate /
                source.sampleRate
            )
        );


    const context =
        new OfflineAudioContext(
            source.numberOfChannels,
            newLength,
            targetRate
        );


    const sourceNode =
        context.createBufferSource();


    sourceNode.buffer =
        source;


    sourceNode.connect(
        context.destination
    );


    sourceNode.start();


    return await context.startRendering();

}



/*
============================================================
 Frame analysis
============================================================
*/


function analyzeFrame(
    channel,
    start,
    frameSize,
    globalPeak,
    threshold,
    maxComponents,
    sampleRate
) {

    const real =
        new Float64Array(frameSize);


    const imag =
        new Float64Array(frameSize);


    /*
    Periodic Hann
    */


    for (
        let n = 0;
        n < frameSize;
        n++
    ) {

        const index =
            start + n;


        const sample =
            index < channel.length
                ? channel[index]
                : 0;


        const window =
            0.5 *
            (
                1 -
                Math.cos(
                    2 * Math.PI *
                    n / frameSize
                )
            );


        real[n] =
            sample * window;

    }


    /*
    FFT
    */

    fft(real, imag);


    /*
    Positive frequency side
    */

    const half =
        Math.floor(frameSize / 2);


    const candidates = [];


    let maxAmplitude = 0;


    for (
        let k = 0;
        k <= half;
        k++
    ) {

        let amplitude =
            Math.hypot(
                real[k],
                imag[k]
            )
            /
            frameSize;


        /*
        Positive-frequency components
        */

        if (
            k !== 0 &&
            k !== half
        ) {

            amplitude *= 2;

        }


        /*
        Normalize against input peak
        */

        amplitude /=
            Math.max(
                globalPeak,
                1e-30
            );


        maxAmplitude =
            Math.max(
                maxAmplitude,
                amplitude
            );


        candidates.push({

            bin: k,

            amplitude,

            real: real[k],

            imag: imag[k]

        });

    }



    /*
    Relative threshold
    */

    const cutoff =
        maxAmplitude *
        threshold;


    let selected =
        candidates.filter(
            component =>
                component.amplitude >=
                cutoff
        );


    /*
    Largest components first
    */

    selected.sort(
        (a, b) =>
            b.amplitude -
            a.amplitude
    );


    /*
    Component limit
    */

    if (
        selected.length >
        maxComponents
    ) {

        selected =
            selected.slice(
                0,
                maxComponents
            );

    }


    /*
    Save in frequency order
    */

    selected.sort(
        (a, b) =>
            a.bin -
            b.bin
    );



    /*
    Convert to KASF component
    */

    return selected.map(
        component => {

            const frequency =
                component.bin *
                sampleRate /
                frameSize;


            /*
            FFT complex phase → sine phase

            FFT uses cosine-like phase.
            KASF synthesis uses:

                A sin(...)
            */

            let phase =
                Math.atan2(
                    component.imag,
                    component.real
                )
                +
                Math.PI / 2;


            phase =
                (
                    phase %
                    (2 * Math.PI)
                    +
                    2 * Math.PI
                )
                %
                (2 * Math.PI);


            return {

                frequency,

                amplitude:
                    Math.min(
                        1,
                        component.amplitude
                    ),

                phase

            };

        }
    );

}



/*
============================================================
 Decode audio
============================================================
*/


async function decodeBlob(
    blob,
    name
) {

    const context =
        new AudioContext();


    try {

        const arrayBuffer =
            await blob.arrayBuffer();


        const audioBuffer =
            await context.decodeAudioData(
                arrayBuffer
            );


        state.audioBuffer =
            audioBuffer;


        state.sourceName =
            name;


        $("generate").disabled =
            false;


        $("play").disabled =
            false;


        $("inputInfo").textContent =

            `${name} / ` +
            `${audioBuffer.numberOfChannels}ch / ` +
            `${audioBuffer.sampleRate} Hz / ` +
            `${audioBuffer.length} samples / ` +
            `${audioBuffer.duration.toFixed(3)} s`;


        log(
            `入力: ${name}`,
            true
        );

    }

    finally {

        await context.close();

    }

}



/*
============================================================
 File loading
============================================================
*/


async function loadFile(file) {

    try {

        await decodeBlob(
            file,
            file.name
        );

    }

    catch (error) {

        log(
            "読み込み失敗: " +
            (
                error.stack ||
                error.message
            ),
            true
        );


        alert(
            "このブラウザでデコードできない音声形式です。"
        );

    }

}



/*
============================================================
 KASF generation
============================================================
*/


async function generateKASF() {

    if (!state.audioBuffer) {
        return;
    }


    $("generate").disabled =
        true;


    $("download").disabled =
        true;


    setProgress(0);


    log(
        "KASF生成開始",
        true
    );


    /*
    Settings
    */

    const original =
        state.audioBuffer;


    const frameDuration =
        Number(
            $("frameMs").value
        ) / 1000;


    const rateSetting =
        $("rate").value;


    const sampleRate =
        rateSetting === "native"
            ? original.sampleRate
            : Number(rateSetting);


    const maxComponents =
        Math.max(
            1,
            Math.min(
                10000,
                Number(
                    $("maxComponents").value
                ) || 256
            )
        );


    const threshold =
        Math.max(
            0,
            Math.min(
                1,
                Number(
                    $("threshold").value
                ) || 0
            )
        );


    /*
    Resampling
    */

    let audio =
        original;


    if (
        audio.sampleRate !==
        sampleRate
    ) {

        log(
            `Resampling: ${audio.sampleRate} -> ${sampleRate}`
        );


        audio =
            await resampleBuffer(
                audio,
                sampleRate
            );

    }



    /*
    Frame size
    */

    const frameSize =
        Math.max(
            2,
            Math.round(
                frameDuration *
                sampleRate
            )
        );


    /*
    50% overlap
    */

    const hop =
        Math.max(
            1,
            Math.round(
                frameSize / 2
            )
        );


    /*
    Frame count

    Frame start:

        round(
            frameIndex *
            T *
            Fs
        )

    */

    const frameCount =
        Math.max(
            1,
            Math.ceil(
                Math.max(
                    0,
                    audio.length -
                    frameSize
                )
                /
                hop
            ) + 1
        );


    const channelCount =
        audio.numberOfChannels;



    /*
    Find global input peak
    */

    let globalPeak = 0;


    for (
        let c = 0;
        c < channelCount;
        c++
    ) {

        const data =
            audio.getChannelData(c);


        for (
            let i = 0;
            i < data.length;
            i++
        ) {

            globalPeak =
                Math.max(
                    globalPeak,
                    Math.abs(
                        data[i]
                    )
                );

        }

    }


    if (
        globalPeak <
        1e-12
    ) {

        globalPeak = 1;

    }



    log(
        `Channels = ${channelCount}`
    );


    log(
        `Sample Rate = ${sampleRate}`
    );


    log(
        `Frame Size = ${frameSize}`
    );


    log(
        `Hop = ${hop}`
    );


    log(
        `Frames = ${frameCount}`
    );


    log(
        `Input Peak = ${globalPeak}`
    );



    /*
    Output chunks
    */

    const chunks = [];



    /*
    KASF Header

    32 bytes

    00 uint32 Magic
    04 uint32 Version
    08 uint64 Channels
    10 uint64 Frames
    18 float64 Frame Duration
    */

    const header =
        new ArrayBuffer(32);


    const headerView =
        new DataView(header);


    /*
    ASCII "KASF"

    Little endian representation
    */

    headerView.setUint32(
        0,
        0x4653414B,
        true
    );


    headerView.setUint32(
        4,
        1,
        true
    );


    writeU64(
        headerView,
        8,
        channelCount
    );


    writeU64(
        headerView,
        16,
        frameCount
    );


    headerView.setFloat64(
        24,
        frameDuration,
        true
    );


    chunks.push(
        new Uint8Array(header)
    );



    /*
    Generate frames
    */

    let totalComponents = 0;


    for (
        let frameIndex = 0;
        frameIndex < frameCount;
        frameIndex++
    ) {


        /*
        IMPORTANT:

        Use absolute time based
        frame position.

        This follows KASF spec.
        */

        const start =
            Math.round(
                frameIndex *
                frameDuration *
                sampleRate
            );



        /*
        Channel
        */

        for (
            let channelIndex = 0;
            channelIndex < channelCount;
            channelIndex++
        ) {


            const channel =
                audio.getChannelData(
                    channelIndex
                );


            const components =
                analyzeFrame(
                    channel,
                    start,
                    frameSize,
                    globalPeak,
                    threshold,
                    maxComponents,
                    sampleRate
                );



            /*
            uint64 Component Count
            */

            const countBuffer =
                new ArrayBuffer(8);


            const countView =
                new DataView(
                    countBuffer
                );


            countView.setBigUint64(
                0,
                BigInt(
                    components.length
                ),
                true
            );


            chunks.push(
                new Uint8Array(
                    countBuffer
                )
            );



            /*
            Components
            */

            for (
                const component
                of components
            ) {

                chunks.push(
                    packComponent(
                        component.frequency,
                        component.amplitude,
                        component.phase
                    )
                );

            }


            totalComponents +=
                components.length;

        }



        /*
        Keep browser responsive
        */

        if (
            frameIndex % 4 === 0 ||
            frameIndex === frameCount - 1
        ) {

            setProgress(
                (frameIndex + 1) /
                frameCount
            );


            log(
                `Frame ${frameIndex + 1} / ${frameCount}`
            );


            await new Promise(
                resolve =>
                    setTimeout(
                        resolve,
                        0
                    )
            );

        }

    }



    /*
    Make Blob
    */

    state.blob =
        new Blob(
            chunks,
            {
                type:
                    "application/octet-stream"
            }
        );



    /*
    Result
    */

    $("result").textContent =

        `完了: ` +
        `${state.blob.size.toLocaleString()} bytes / ` +
        `${frameCount} frames / ` +
        `${channelCount} channels / ` +
        `${totalComponents.toLocaleString()} components`;


    $("download").disabled =
        false;


    $("generate").disabled =
        false;


    log(
        "KASF生成完了"
    );

}



/*
============================================================
 Playback
============================================================
*/


function playInput() {

    if (!state.audioBuffer) {
        return;
    }


    const context =
        new AudioContext();


    const source =
        context.createBufferSource();


    source.buffer =
        state.audioBuffer;


    source.connect(
        context.destination
    );


    source.onended =
        () => context.close();


    source.start();

}



/*
============================================================
 Recording
============================================================
*/


async function startRecording() {

    if (
        !navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia
    ) {

        alert(
            "このブラウザでは録音APIを利用できません。"
        );

        return;

    }


    try {

        const stream =
            await navigator.mediaDevices.getUserMedia({
                audio: true
            });


        /*
        Browser dependent formats
        */

        const types = [

            "audio/webm;codecs=opus",

            "audio/webm",

            "audio/ogg;codecs=opus",

            "audio/ogg"

        ];


        const supported =
            types.find(
                type =>
                    MediaRecorder.isTypeSupported(
                        type
                    )
            );


        state.chunks = [];


        state.recorder =
            supported
                ? new MediaRecorder(
                    stream,
                    {
                        mimeType:
                            supported
                    }
                )
                : new MediaRecorder(
                    stream
                );



        state.recorder.ondataavailable =
            event => {

                if (
                    event.data.size
                ) {

                    state.chunks.push(
                        event.data
                    );

                }

            };



        state.recorder.onstop =
            async () => {

                stream
                    .getTracks()
                    .forEach(
                        track =>
                            track.stop()
                    );


                try {

                    const blob =
                        new Blob(
                            state.chunks,
                            {
                                type:
                                    state.recorder.mimeType
                            }
                        );


                    const extension =
                        blob.type.includes("ogg")
                            ? "ogg"
                            : "webm";


                    await decodeBlob(
                        blob,
                        `recording.${extension}`
                    );

                }

                catch (error) {

                    log(
                        "録音データのデコード失敗: " +
                        error.message,
                        true
                    );


                    alert(
                        "録音データをデコードできませんでした。"
                    );

                }

            };



        state.recorder.start();


        $("recordStart").disabled =
            true;


        $("recordStop").disabled =
            false;


        log(
            "録音開始"
        );

    }

    catch (error) {

        log(
            "録音開始失敗: " +
            error.message,
            true
        );


        alert(
            "マイクへのアクセスが許可されませんでした。"
        );

    }

}



/*
============================================================
 Recording stop
============================================================
*/


function stopRecording() {

    if (
        state.recorder &&
        state.recorder.state ===
        "recording"
    ) {

        state.recorder.stop();


        $("recordStart").disabled =
            false;


        $("recordStop").disabled =
            true;


        log(
            "録音停止。デコード中..."
        );

    }

}



/*
============================================================
 File input
============================================================
*/


$("file").onchange =
    event => {

        const file =
            event.target.files?.[0];


        if (file) {

            loadFile(file);

        }

    };



/*
============================================================
 Drag & Drop
============================================================
*/


$("drop").ondragover =
    event => {

        event.preventDefault();

        $("drop").classList.add(
            "drag"
        );

    };


$("drop").ondragleave =
    () => {

        $("drop").classList.remove(
            "drag"
        );

    };


$("drop").ondrop =
    event => {

        event.preventDefault();


        $("drop").classList.remove(
            "drag"
        );


        const file =
            event.dataTransfer.files?.[0];


        if (file) {

            loadFile(file);

        }

    };



/*
============================================================
 Buttons
============================================================
*/


$("recordStart").onclick =
    startRecording;


$("recordStop").onclick =
    stopRecording;


$("play").onclick =
    playInput;



/*
============================================================
 Clear
============================================================
*/


$("clear").onclick =
    () => {

        state.audioBuffer =
            null;


        state.sourceName =
            "";


        state.blob =
            null;


        $("generate").disabled =
            true;


        $("play").disabled =
            true;


        $("download").disabled =
            true;


        $("file").value =
            "";


        $("inputInfo").textContent =
            "入力なし";


        $("result").textContent =
            "未生成";


        setProgress(0);


        log(
            "消去",
            true
        );

    };



/*
============================================================
 Generate button
============================================================
*/


$("generate").onclick =
    () => {

        generateKASF()
            .catch(
                error => {

                    log(
                        "生成失敗: " +
                        (
                            error.stack ||
                            error.message
                        ),
                        true
                    );


                    $("generate").disabled =
                        false;

                }
            );

    };



/*
============================================================
 Download
============================================================
*/


$("download").onclick =
    () => {

        if (!state.blob) {
            return;
        }


        const base =
            (
                state.sourceName ||
                "output"
            )
            .replace(
                /\.[^.]+$/,
                ""
            );


        const url =
            URL.createObjectURL(
                state.blob
            );


        const link =
            document.createElement(
                "a"
            );


        link.href =
            url;


        link.download =
            base + ".kasf";


        link.click();


        setTimeout(
            () =>
                URL.revokeObjectURL(
                    url
                ),
            5000
        );

    };