/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useRef, useEffect } from 'react';
import { 
  Mic, 
  Square, 
  Copy, 
  Check, 
  Settings, 
  Sparkles, 
  Type, 
  Volume2, 
  History,
  Trash2,
  ChevronRight,
  Zap,
  Shield
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

type Vibe = 'raw' | 'natural' | 'professional' | 'concise' | 'creative' | 'casual';

interface Transcription {
  id: string;
  original: string;
  refined: string;
  vibe: Vibe;
  timestamp: number;
}

export default function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcription, setTranscription] = useState('');
  const [refinedText, setRefinedText] = useState('');
  const [selectedVibe, setSelectedVibe] = useState<Vibe>('natural');
  const [history, setHistory] = useState<Transcription[]>([]);
  const [copied, setCopied] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [permissionStatus, setPermissionStatus] = useState<'prompt' | 'granted' | 'denied' | 'unknown'>('unknown');

  useEffect(() => {
    console.log(`State changed: isRecording=${isRecording}, isProcessing=${isProcessing}`);
  }, [isRecording, isProcessing]);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  // Load history from local storage
  useEffect(() => {
    const saved = localStorage.getItem('vibewhisper_history');
    if (saved) {
      try {
        setHistory(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to load history", e);
      }
    }
  }, []);

  // Save history to local storage
  useEffect(() => {
    localStorage.setItem('vibewhisper_history', JSON.stringify(history));
  }, [history]);

  // Check permission status on mount
  useEffect(() => {
    if (navigator.permissions && navigator.permissions.query) {
      navigator.permissions.query({ name: 'microphone' as PermissionName }).then((result) => {
        setPermissionStatus(result.state as any);
        result.onchange = () => setPermissionStatus(result.state as any);
      }).catch(() => setPermissionStatus('unknown'));
    }
  }, []);

  const startRecording = async () => {
    setError(null);
    console.log("Attempting to start recording...");
    
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError("Your browser does not support audio recording.");
      return;
    }

    if (typeof MediaRecorder === 'undefined') {
      setError("This browser cannot record audio (MediaRecorder is unavailable).");
      return;
    }

    if (!window.isSecureContext) {
      setError("Microphone access requires a secure context. Open the app at http://localhost:3000.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setPermissionStatus('granted');
      
      const mimeCandidates = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/mp4',
        'audio/ogg;codecs=opus',
      ];
      const supportedMime = mimeCandidates.find((candidate) => MediaRecorder.isTypeSupported(candidate));

      let mediaRecorder: MediaRecorder;
      try {
        mediaRecorder = supportedMime ? new MediaRecorder(stream, { mimeType: supportedMime }) : new MediaRecorder(stream);
      } catch (createErr) {
        stream.getTracks().forEach(track => track.stop());
        console.error("Failed to initialize MediaRecorder:", createErr);
        setError("Could not initialize microphone recording in this browser.");
        return;
      }

      const mimeType = mediaRecorder.mimeType || supportedMime || 'audio/webm';
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      // Audio visualization setup
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      
      audioContextRef.current = audioContext;
      analyserRef.current = analyser;

      const updateLevel = () => {
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(dataArray);
        const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
        setAudioLevel(average / 128);
        animationFrameRef.current = requestAnimationFrame(updateLevel);
      };
      updateLevel();

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onerror = (event) => {
        console.error("MediaRecorder error:", event);
        setError("Microphone recording failed. Please try again.");
        setIsRecording(false);
      };

      mediaRecorder.onstop = async () => {
        if (audioChunksRef.current.length === 0) {
          setError("No audio was captured. Please allow mic access and try again.");
          if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
          if (audioContextRef.current) audioContextRef.current.close();
          stream.getTracks().forEach(track => track.stop());
          return;
        }

        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        processAudio(audioBlob, mimeType);
        
        if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
        if (audioContextRef.current) audioContextRef.current.close();
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      console.log("Recording started successfully");
    } catch (err) {
      console.error("Error accessing microphone:", err);
      const domErr = err as DOMException;
      if (domErr?.name === 'NotAllowedError') {
        setPermissionStatus('denied');
        setError("Microphone access was blocked. Please allow mic access in your browser.");
      } else if (domErr?.name === 'NotFoundError') {
        setError("No microphone device was found on this system.");
      } else if (domErr?.name === 'NotReadableError') {
        setError("Microphone is busy or unavailable. Close other apps using it and try again.");
      } else {
        setError("Could not start recording. Check mic permissions and try again.");
      }
    }
  };

  const stopRecording = () => {
    console.log("Stopping recording...");
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const processAudio = async (blob: Blob, mimeType: string) => {
    console.log(`Processing audio blob of size ${blob.size} with type ${mimeType}`);
    setIsProcessing(true);
    setError(null);

    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result as string);
        reader.onerror = () => reject(new Error("Failed to read recorded audio."));
        reader.readAsDataURL(blob);
      });

      const base64Data = dataUrl.split(',')[1];
      const response = await fetch('/api/process-audio', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          audioBase64: base64Data,
          mimeType,
          vibe: selectedVibe,
        }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || 'Local processing failed.');
      }

      const result = await response.json();
      setTranscription(result.transcription || '');
      setRefinedText(result.refined || '');

      if (result.transcription) {
        const newEntry: Transcription = {
          id: Date.now().toString(),
          original: result.transcription,
          refined: result.refined || result.transcription,
          vibe: selectedVibe,
          timestamp: Date.now()
        };
        setHistory(prev => [newEntry, ...prev].slice(0, 20));
      }
    } catch (err) {
      console.error("Error processing audio:", err);
      setError(err instanceof Error ? err.message : "Failed to process audio locally.");
    } finally {
      setIsProcessing(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const clearHistory = () => {
    if (confirm("Clear all transcription history?")) {
      setHistory([]);
    }
  };

  const vibes: { id: Vibe; label: string; icon: any; desc: string }[] = [
    { id: 'raw', label: 'Raw', icon: Mic, desc: 'Exactly as spoken, no changes' },
    { id: 'natural', label: 'Natural', icon: Type, desc: 'Cleaned up but keeps your voice' },
    { id: 'professional', label: 'Pro', icon: Shield, desc: 'Formal, polished, and precise' },
    { id: 'concise', label: 'Concise', icon: Zap, desc: 'Short, direct, and to the point' },
    { id: 'creative', label: 'Creative', icon: Sparkles, desc: 'Engaging, vivid, and expressive' },
    { id: 'casual', label: 'Casual', icon: Volume2, desc: 'Friendly and conversational' },
  ];

  return (
    <div className="min-h-screen flex flex-col items-center p-4 md:p-8 max-w-5xl mx-auto">
      {/* Header */}
      <header className="w-full flex justify-between items-center mb-12">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-900/20">
            <Mic className="text-white w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">VibeWhisper</h1>
            <p className="text-xs text-zinc-500 font-mono uppercase tracking-widest">Ubuntu Desktop AI</p>
          </div>
        </div>
        <div className="flex gap-4">
          <button className="p-2 rounded-full hover:bg-zinc-800 text-zinc-400 transition-colors">
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </header>

      <main className="w-full grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: Controls & Presets */}
        <div className="lg:col-span-4 space-y-6">
          <div className="hardware-card rounded-3xl p-6 space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">Processing Mode</label>
              <div className="grid grid-cols-1 gap-2">
                {vibes.map((vibe) => (
                  <button
                    key={vibe.id}
                    onClick={() => setSelectedVibe(vibe.id)}
                    className={`flex items-center gap-3 p-3 rounded-2xl transition-all text-left ${
                      selectedVibe === vibe.id 
                        ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40' 
                        : 'hover:bg-zinc-800 text-zinc-400'
                    }`}
                  >
                    <vibe.icon className="w-5 h-5" />
                    <div>
                      <div className="text-sm font-semibold">{vibe.label}</div>
                      <div className={`text-[10px] ${selectedVibe === vibe.id ? 'text-blue-100' : 'text-zinc-500'}`}>
                        {vibe.desc}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="pt-4 border-t border-zinc-800">
              <div className="flex items-center justify-between mb-4">
                <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">Local GPU Status</label>
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                  <span className="text-[10px] font-mono text-green-500">LOCAL PIPELINE READY</span>
                </div>
              </div>
              <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
                <motion.div 
                  className="h-full bg-blue-500"
                  animate={{ width: isRecording ? `${audioLevel * 100}%` : '0%' }}
                />
              </div>
            </div>
          </div>

          <div className="hardware-card rounded-3xl p-6">
             <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-500 flex items-center gap-2">
                  <History className="w-3 h-3" /> History
                </h3>
                <button onClick={clearHistory} className="text-zinc-600 hover:text-red-400 transition-colors">
                  <Trash2 className="w-4 h-4" />
                </button>
             </div>
             <div className="space-y-3 max-h-[300px] overflow-y-auto pr-2">
                {history.length === 0 ? (
                  <p className="text-xs text-zinc-600 italic">No recent captures</p>
                ) : (
                  history.map((item) => (
                    <button 
                      key={item.id}
                      onClick={() => {
                        setTranscription(item.original);
                        setRefinedText(item.refined);
                        setSelectedVibe(item.vibe);
                      }}
                      className="w-full text-left p-3 rounded-xl bg-zinc-900/50 hover:bg-zinc-800 border border-zinc-800/50 transition-all group"
                    >
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[10px] font-mono text-zinc-500">
                          {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 uppercase tracking-tighter">
                          {item.vibe}
                        </span>
                      </div>
                      <p className="text-xs text-zinc-300 line-clamp-2 leading-relaxed">
                        {item.refined || item.original}
                      </p>
                    </button>
                  ))
                )}
             </div>
          </div>
        </div>

        {/* Right Column: Main Interaction */}
        <div className="lg:col-span-8 space-y-6">
          {/* Recording Area */}
          <div className="hardware-card rounded-[40px] p-12 flex flex-col items-center justify-center relative overflow-hidden min-h-[400px]">
            {/* Background Glow */}
            <AnimatePresence>
              {isRecording && (
                <motion.div 
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 bg-gradient-to-b from-red-500/5 to-transparent pointer-events-none"
                />
              )}
            </AnimatePresence>

            <div className={`relative z-10 flex flex-col items-center gap-8 ${isRecording ? 'is-recording' : ''}`}>
              <div className="relative">
                <div className="record-ring pointer-events-none absolute -inset-4 border-2 border-zinc-800 rounded-full" />
                <button
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={isProcessing}
                  className={`w-24 h-24 rounded-full flex items-center justify-center transition-all duration-500 shadow-2xl ${
                    isRecording 
                      ? 'bg-red-500 scale-90 shadow-red-900/40' 
                      : 'bg-blue-600 hover:bg-blue-500 shadow-blue-900/40'
                  } ${isProcessing ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer active:scale-95'}`}
                >
                  {isRecording ? (
                    <Square className="text-white w-8 h-8 fill-current" />
                  ) : (
                    <Mic className="text-white w-10 h-10" />
                  )}
                </button>
              </div>

              <div className="text-center space-y-2">
                <h2 className="text-2xl font-bold tracking-tight">
                  {isRecording ? "Listening..." : isProcessing ? "Refining with AI..." : "Ready to Capture"}
                </h2>
                <p className="text-zinc-500 text-sm max-w-xs mx-auto">
                  {error ? (
                    <span className="text-red-400 font-medium">{error}</span>
                  ) : isRecording 
                    ? "Speak clearly. Your local GPU is optimizing the stream." 
                    : isProcessing 
                    ? "Applying the " + selectedVibe + " vibe locally."
                    : permissionStatus === 'denied'
                    ? "Microphone access is blocked. Please enable it in your browser."
                    : "Tap the button to start dictating your thoughts."}
                </p>
              </div>

              {/* Visualizer */}
              {isRecording && (
                <div className="flex items-end gap-1 h-8">
                  {[...Array(12)].map((_, i) => (
                    <motion.div
                      key={i}
                      animate={{ 
                        height: [8, Math.random() * 32 + 8, 8],
                      }}
                      transition={{ 
                        repeat: Infinity, 
                        duration: 0.5, 
                        delay: i * 0.05 
                      }}
                      className="w-1 bg-red-500/60 rounded-full"
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Result Area */}
          <AnimatePresence>
            {(refinedText || transcription) && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-4"
              >
                <div className="hardware-card rounded-3xl p-8 relative group">
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-blue-500" />
                      <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-500">Refined Output</span>
                    </div>
                    <button 
                      onClick={() => copyToClipboard(refinedText || transcription)}
                      className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-xl text-xs font-semibold transition-all"
                    >
                      {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
                      {copied ? "Copied" : "Copy to Clipboard"}
                    </button>
                  </div>
                  
                  <div className="space-y-6">
                    <p className="text-lg leading-relaxed text-zinc-100 font-medium">
                      {refinedText || transcription}
                    </p>
                    
                    {transcription && refinedText && (
                      <div className="pt-6 border-t border-zinc-800/50">
                        <details className="group">
                          <summary className="text-[10px] font-mono uppercase tracking-widest text-zinc-600 cursor-pointer hover:text-zinc-400 transition-colors flex items-center gap-2 list-none">
                            <ChevronRight className="w-3 h-3 group-open:rotate-90 transition-transform" />
                            Show Original Transcription
                          </summary>
                          <p className="mt-4 text-sm text-zinc-500 italic leading-relaxed">
                            "{transcription}"
                          </p>
                        </details>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Footer Info */}
      <footer className="mt-auto py-8 w-full border-t border-zinc-900 flex flex-col md:flex-row justify-between items-center gap-4">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-600">
            <Shield className="w-3 h-3" /> Privacy Focused
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-600">
            <Zap className="w-3 h-3" /> Low Latency
          </div>
          <div className="flex items-center gap-2 text-[10px] font-mono text-zinc-600">
            <span className="opacity-50">Mic Status:</span> 
            <span className={permissionStatus === 'granted' ? 'text-green-500' : permissionStatus === 'denied' ? 'text-red-500' : 'text-zinc-400'}>
              {permissionStatus.toUpperCase()}
            </span>
          </div>
        </div>
        <p className="text-[10px] font-mono text-zinc-700">
          VIBEWHISPER V1.0.5 // UBUNTU 24.04 OPTIMIZED
        </p>
      </footer>
    </div>
  );
}
