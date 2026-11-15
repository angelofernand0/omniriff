/**
 * Media device enumeration and acquisition.
 * Supports USB audio interfaces (Focusrite Scarlett Solo, etc.) and webcams.
 * Guarantees zero automatic acquisition: runs strictly upon explicit user interaction.
 */

export interface DeviceInfo {
  deviceId: string;
  label: string;
}

export class DeviceManager {
  public audioInputs: DeviceInfo[] = [];
  public audioOutputs: DeviceInfo[] = [];
  public videoInputs: DeviceInfo[] = [];

  public selectedAudioInputId: string | null = null;
  public selectedAudioOutputId: string | null = null;
  public selectedVideoInputId: string | null = null;

  public selectedChannel: number = 0; // 0 = default / Ch 1, 1 = Ch 2 (Scarlett Instrument input)

  constructor() {}

  public async enumerate(): Promise<void> {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
      return;
    }
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      this.audioInputs = [];
      this.audioOutputs = [];
      this.videoInputs = [];

      let micIdx = 1, outIdx = 1, camIdx = 1;
      for (const d of devices) {
        if (d.kind === 'audioinput') {
          this.audioInputs.push({
            deviceId: d.deviceId,
            label: d.label || `Audio Input ${micIdx++}`,
          });
        } else if (d.kind === 'audiooutput') {
          this.audioOutputs.push({
            deviceId: d.deviceId,
            label: d.label || `Audio Output ${outIdx++}`,
          });
        } else if (d.kind === 'videoinput') {
          this.videoInputs.push({
            deviceId: d.deviceId,
            label: d.label || `Camera ${camIdx++}`,
          });
        }
      }

      if (this.audioInputs.length > 0 && !this.selectedAudioInputId) {
        this.selectedAudioInputId = this.audioInputs[0].deviceId;
      }
      if (this.audioOutputs.length > 0 && !this.selectedAudioOutputId) {
        this.selectedAudioOutputId = this.audioOutputs[0].deviceId;
      }
      if (this.videoInputs.length > 0 && !this.selectedVideoInputId) {
        this.selectedVideoInputId = this.videoInputs[0].deviceId;
      }
    } catch (e) {
      console.warn('Failed to enumerate devices:', e);
    }
  }

  public async getAudioStream(): Promise<MediaStream> {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('navigator.mediaDevices.getUserMedia is not supported in this browser.');
    }

    const constraints: MediaStreamConstraints = {
      audio: {
        echoCancellation: false,
        autoGainControl: false,
        noiseSuppression: false,
        deviceId: this.selectedAudioInputId ? { exact: this.selectedAudioInputId } : undefined,
      },
      video: false,
    };

    try {
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      // Re-enumerate to get friendly labels if previously permission was not granted
      await this.enumerate();
      return stream;
    } catch (err: any) {
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        throw new Error('Microphone permission was denied. Please allow microphone access to use Live Rig.');
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        throw new Error('No audio input device found. Please plug in an audio interface or microphone.');
      }
      throw err;
    }
  }

  public async getVideoStream(): Promise<MediaStream> {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('navigator.mediaDevices.getUserMedia is not supported in this browser.');
    }

    const constraints: MediaStreamConstraints = {
      audio: false,
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        frameRate: { ideal: 30 },
        deviceId: this.selectedVideoInputId ? { exact: this.selectedVideoInputId } : undefined,
      },
    };

    try {
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      await this.enumerate();
      return stream;
    } catch (err: any) {
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        throw new Error('Camera permission was denied. Please allow camera access to use webcam hand tracking.');
      }
      throw err;
    }
  }

  public async setAudioOutput(ctx: AudioContext, deviceId: string): Promise<boolean> {
    if ('setSinkId' in ctx && typeof (ctx as any).setSinkId === 'function') {
      try {
        await (ctx as any).setSinkId(deviceId);
        this.selectedAudioOutputId = deviceId;
        return true;
      } catch (e) {
        console.warn('Failed to set audio sink ID:', e);
        return false;
      }
    }
    return false;
  }
}
