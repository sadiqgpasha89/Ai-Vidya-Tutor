# AIVidya mobile app (Android / iOS shells)

AIVidya is a Progressive Web App: on Android Chrome or iOS Safari students can already use **Add to Home screen / Install app**.
This folder wraps the same web app in native shells with [Capacitor](https://capacitorjs.com) for Play Store / App Store distribution.
The shell loads your deployed server (it needs HTTPS), so the web app is the single source of truth.

**Status: scaffold only.** It has not been built or tested here (that needs the Android SDK / Xcode).

```bash
cd mobile
npm install
# 1. edit capacitor.config.json: server.url -> your https:// AIVidya server, appId/appName -> yours
npx cap add android      # and/or: npx cap add ios   (macOS + Xcode)
npx cap sync
npx cap open android     # build / run / sign in Android Studio
```

Before publishing: add app icons (`/frontend/icons/icon-512.png` is a starting point), give the app a privacy policy URL
(`/#/legal/privacy`), and check the microphone permission strings (Android `RECORD_AUDIO`, iOS `NSMicrophoneUsageDescription`)
because voice input and the voice check need them. Browser speech recognition is not available in every WebView, so
turn on **private voice input** (Whisper on your server) in Settings → Voice for the mobile apps.
