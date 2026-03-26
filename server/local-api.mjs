import express from 'express';
import os from 'os';
import path from 'path';
import { promises as fs } from 'fs';
import { randomUUID } from 'crypto';
import { spawn } from 'child_process';

const app = express();
const port = Number(process.env.LOCAL_API_PORT || 5174);

app.use(express.json({ limit: '30mb' }));

const mimeToExtension = {
  'audio/webm': 'webm',
  'audio/mp4': 'm4a',
  'audio/mpeg': 'mp3',
  'audio/wav': 'wav',
  'audio/x-wav': 'wav',
  'audio/ogg': 'ogg',
};

const vibeInstructions = {
  raw: 'Return the text exactly as-is. Do not change wording, punctuation, or casing.',
  natural: 'Lightly clean up grammar and punctuation while preserving the original voice and meaning.',
  professional: 'Rewrite into a formal, polished, professional tone while preserving meaning.',
  concise: 'Rewrite to be short, direct, and clear while keeping all key meaning.',
  creative: 'Rewrite with engaging and expressive language while preserving meaning.',
  casual: 'Rewrite in a friendly and conversational style while preserving meaning.',
};

function runTranscription(audioPath) {
  const pythonBin = process.env.PYTHON_BIN || 'python3';
  const model = process.env.WHISPER_MODEL || 'small';
  const device = process.env.WHISPER_DEVICE || 'cuda';
  const computeType = process.env.WHISPER_COMPUTE_TYPE || (device === 'cuda' ? 'float16' : 'int8');
  const language = process.env.WHISPER_LANGUAGE || 'en';

  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin, [
      'scripts/transcribe.py',
      '--audio', audioPath,
      '--model', model,
      '--device', device,
      '--compute-type', computeType,
      '--language', language,
    ]);

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });

    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    child.on('error', (err) => reject(err));

    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `Transcription process failed with exit code ${code}`));
        return;
      }

      try {
        const parsed = JSON.parse(stdout);
        resolve(parsed);
      } catch (error) {
        reject(new Error(`Failed to parse transcription JSON: ${error instanceof Error ? error.message : String(error)}`));
      }
    });
  });
}

async function refineWithOllama(text, vibe) {
  if (!text || vibe === 'raw') {
    return text;
  }

  const ollamaBaseUrl = process.env.OLLAMA_URL || 'http://127.0.0.1:11434';
  const ollamaModel = process.env.OLLAMA_MODEL || 'llama3.2:3b';
  const instruction = vibeInstructions[vibe] || vibeInstructions.natural;

  const prompt = [
    'You are a text editor.',
    instruction,
    'Return only the rewritten text. Do not add commentary or quotes.',
    '',
    `Input: ${text}`,
  ].join('\n');

  const response = await fetch(`${ollamaBaseUrl}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: ollamaModel,
      prompt,
      stream: false,
      options: {
        temperature: 0.2,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`Ollama request failed with HTTP ${response.status}`);
  }

  const data = await response.json();
  return typeof data.response === 'string' && data.response.trim() ? data.response.trim() : text;
}

app.get('/api/health', async (_req, res) => {
  const device = process.env.WHISPER_DEVICE || 'cuda';
  const model = process.env.WHISPER_MODEL || 'small';
  const ollamaModel = process.env.OLLAMA_MODEL || 'llama3.2:3b';
  res.json({
    ok: true,
    mode: 'local-only',
    whisper: { device, model },
    ollama: { model: ollamaModel, url: process.env.OLLAMA_URL || 'http://127.0.0.1:11434' },
  });
});

app.post('/api/process-audio', async (req, res) => {
  const { audioBase64, mimeType, vibe } = req.body || {};

  if (!audioBase64 || typeof audioBase64 !== 'string') {
    res.status(400).send('Missing "audioBase64" in request body.');
    return;
  }

  const ext = mimeToExtension[mimeType] || 'webm';
  const tempPath = path.join(os.tmpdir(), `vibewhisper-${randomUUID()}.${ext}`);

  try {
    await fs.writeFile(tempPath, Buffer.from(audioBase64, 'base64'));

    const transcriptResult = await runTranscription(tempPath);
    const transcription = (transcriptResult.transcription || '').trim();

    if (!transcription) {
      res.status(500).send('No transcription was produced by local Whisper.');
      return;
    }

    let refined = transcription;
    try {
      refined = await refineWithOllama(transcription, vibe || 'natural');
    } catch (refineErr) {
      console.warn('Refinement failed, returning transcription only:', refineErr);
      refined = transcription;
    }

    res.json({
      transcription,
      refined,
      vibe: vibe || 'natural',
      provider: {
        transcription: 'faster-whisper (local)',
        refinement: refined === transcription ? 'none-or-fallback' : 'ollama (local)',
      },
    });
  } catch (err) {
    console.error('Error processing local audio:', err);
    res.status(500).send(err instanceof Error ? err.message : 'Local processing failed.');
  } finally {
    await fs.unlink(tempPath).catch(() => {});
  }
});

app.listen(port, () => {
  console.log(`[local-api] listening on http://127.0.0.1:${port}`);
  console.log('[local-api] mode: fully local (Whisper + optional Ollama).');
});
