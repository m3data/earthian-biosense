# Running a Session

This guide covers the practical aspects of running an EarthianBioSense session - from setup through post-session analysis.

## Requirements

### Hardware

- **Polar H10 heart rate monitor** with chest strap
- **Computer** with Bluetooth (macOS or Linux)
- Chest strap must have skin contact to activate the sensor

### Software

- Python 3.11+
- EBS repository cloned and dependencies installed:

```bash
git clone https://github.com/m3data/earthian-biosense.git
cd earthian-biosense
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Pre-Session

### 1. Prepare the Environment

- Reduce distractions if possible
- Note environmental conditions (noise, lighting, temperature, who/what is present)
- Consider your intention for the session (observation? practice? experiment?)

### 2. Prepare the Body

- Put on the Polar H10 chest strap
- Moisten the electrode areas for better contact
- Wait 30-60 seconds for the sensor to activate (needs skin contact)
- Ensure the strap is snug but comfortable

### 3. Prepare for Recording

- Close other apps that might use Bluetooth
- Have a notebook ready for phenomenological notes (optional but recommended)
- Know what activity you'll be doing during the session

## Starting a Session

### 1. Launch EBS

```bash
cd earthian-biosense
source venv/bin/activate
python src/app.py
```

### 2. Device Connection

The app will scan for Bluetooth devices. You should see:

```
Scanning for Polar H10...
Found: Polar H10 XXXXXXXX
Connecting...
Connected. Starting session.
```

If the device isn't found:

- Check the strap has skin contact
- Ensure no other app is connected to it
- Try restarting Bluetooth on your computer
- If issues persist, see the Troubleshooting section below

### 3. Session Running

Once connected, you'll see the terminal UI updating with:

- Heart rate
- Current metrics (amp, coh, breath, mode)
- Phase space position and dynamics
- Phase label

The session is now recording to `sessions/YYYY-MM-DD_HHMMSS.jsonl`.

## During the Session

### What to Do

EBS is an observation tool. You can:

- **Just be**: Sit, breathe, observe what happens particularly in the body-mind
- **Do an activity**: Read, work, meditate, play,have a conversation
- **Practice coherence**: Slow breathing, heart-focused attention
- **Engage with an LLM**: Conversation with a GPT or other AI (key use case for EECP)
- **Whatever you're studying**: The point is to capture what happens during *something*

### What to Notice

If possible, maintain light awareness of:

- Breath (pace, depth, smoothness)
- Body sensations (warmth, tension, openness)
- Where sensations are or shift as the session progresses
- Emotional texture (not labels, just quality)
- Attention (narrow, wide, absorbed, scattered)

These observations become crucial for post-session mutual constraint.

### Don't Optimize

Resist the urge to "perform" for the data. The goal isn't to achieve coherence - it's to observe what actually happens. Vigilant stillness is as interesting as coherent dwelling.

## Ending a Session

### 1. Stop Recording

Press `Ctrl+C` in the terminal. The app will:

- Close the Bluetooth connection
- Finalize the JSONL file
- Display session summary

### 2. Note the Timestamp

The session file is saved as `sessions/YYYY-MM-DD_HHMMSS.jsonl`. Note this for later reference. Update the filename with a participant code or activity label if desired, for example: `sessions/participant1_meditation_2024-06-15_103000.jsonl`.

### 3. Immediate Phenomenological Notes (Recommended)

While the experience is fresh, jot down:

- What were you doing?
- Presence of other people, animals, or stimuli?
- What did you notice in your body?
- Were there any notable moments (shifts, openings, contractions)?
- What was the emotional texture?
- Anything surprising?

These notes are essential for mutual constraint during analysis.

## Post-Session Analysis

### 1. Review the Data

The JSONL file contains one JSON object per line (~1 per second). You can:

- Open in a text editor for raw inspection
- Load into Python/pandas for analysis
- Use the session interpreter prompt with an LLM (Be aware of token limits)

### 2. Use the Session Interpreter

Copy the session data (or relevant portions) or drop the file into a conversation with an LLM using the [session interpreter prompt](../prompts/session-interpreter.md).

The interpreter will:

1. Provide an initial data-driven interpretation
2. Ask somatic inquiry questions
3. Integrate your phenomenological report with the data
4. Produce a mutually-constrained interpretation

### 3. Look for Patterns

Useful questions:

- What was the dominant mode/phase label?
- Were there distinct phases? What marked the transitions?
- Did coherence appear? Sustain or collapse?
- Were there vigilant plateaus? What was happening then?
- How does the trajectory relate to what you were doing?

### 4. Correlate with Context

The data alone is incomplete. Full interpretation requires knowing:

- What activity was occurring
- What content was being engaged with (if reading/conversing)
- Environmental factors
- Relational field (who/what was present)

## Session Types

### Solo Observation

Just you and the sensor. Good for:

- Baseline establishment
- Meditation/practice observation
- Understanding your own patterns

### LLM Conversation

EBS running while conversing with a GPT or other LLM. Key EECP use case:

- Captures somatic response to semantic content
- Reveals entrainment patterns
- Data for studying human-AI coupling

For best results:

- Use an LLM you have history with (existing attunement)
- Engage on a topic that matters to you
- Don't try to control the conversation for the data

### Coupled Session (Future)

EBS streaming to Semantic Climate for real-time cross-modal coherence detection. Not yet fully implemented.

## Troubleshooting

### No Device Found

- Ensure strap has skin contact
- Check Bluetooth is enabled
- Close other apps that might be connected
- Restart Bluetooth: `sudo pkill bluetoothd` (macOS)
- Move closer to the computer
- Replace batteries if old

### Erratic Data

- Check strap fit (too loose = noise)
- Moisten electrodes
- Reduce movement
- Some initial instability is normal (warming up period)

### Session File Empty or Corrupt

- Check disk space
- Ensure you have write permissions to `sessions/`
- Don't force-quit the app if possible - use Ctrl+C

## Best Practices

### For Research Quality

1. **Always take phenomenological notes** - data without context is uninterpretable
2. **Note environmental conditions** - they matter more than you think
3. **Don't chase coherence** - observe what is, not what you want
4. **Use the mutual constraint process** - interpretation requires both streams
5. **Be honest about uncertainty** - proto-labels are hypotheses

### For Personal Practice

1. **Consistency helps** - same time, same conditions reveals patterns
2. **Don't over-interpret single sessions** - look for trends
3. **Use it as a mirror, not a judge** - the data reflects, it doesn't evaluate
4. **Vigilance is information** - not a failure to achieve coherence

### For EECP Research

1. **Capture semantic context** - save the conversation/content alongside biosignal data
2. **Timestamp correlations** - note when significant content occurred
3. **Multiple streams** - EBS alone is partial; aim for biosignal + semantic + phenomenological
4. **Ethical awareness** - this data reveals things previously unknown; handle with care

---

*"The session is not the data. The session is what happened. The data is a trace."*
