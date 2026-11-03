"""Privacy notice and terms (templates). The operator of this deployment must review them with legal counsel and add contact details."""
from . import config

_V = config.NOTICE_VERSION

PRIVACY = f"""# Privacy notice (version {_V})

*This is a template written to follow the spirit of India's Digital Personal Data Protection Act, 2023. The school or organisation running this
server is the "data fiduciary" and must review it with legal counsel and add its contact details before use.*

## Who we are
AIVidya is an AI teaching assistant run by **[operator name, address, grievance officer e-mail]**.

## What we collect
- **Account**: username, name, year of birth, role, password (stored only as a salted hash).
- **Learning data**: topics studied, quiz / test / practice results, mistakes, notes, highlights, flashcard history, chat messages with the tutor, XP and badges,
  and a short "tutor memory" note about how you learn (we tell the tutor never to store family names, addresses or phone numbers).
- **Optional**: e-mail / phone for reminders, push-notification address, textbooks or photos you upload, voice recordings you send for speech recognition.
- **Technical**: IP address, browser type and security logs (kept to protect accounts).

## Why
To teach, to show progress to you, your parents and your teachers, to keep revision on schedule, and to keep the service safe. We do not sell data and do not show ads.

## Children (under 18)
A parent or guardian must approve a child's account by entering the child's code on their own account. Until then the child cannot use the tutor.
Parents can see their child's progress and reports, withdraw consent at any time (which locks the account), and have the account erased.

## Safety alerts
If a child's message suggests they may be in distress, the tutor shows help-line numbers (Tele-MANAS 14416, CHILDLINE 1098) and the linked parent receives a
notification that their child may need support. The message itself is **not** shared in that notification.

## AI and third parties
- Lessons, answers and grading are produced by an AI model. **Where it runs**: {"on this server (a local model); your messages are not sent to an outside AI company" if config.PROVIDER == "ollama" else "with an outside AI provider, to which your messages are sent for processing"}.
- Voice: the browser's built-in speech recognition (Chrome/Edge) may send audio to the browser vendor. Choose "private voice input" in settings to have this server transcribe instead.
- AI can be wrong. Content is labelled as AI-generated; teachers may review it.

## Your rights
You can **download all your data** and **delete your account** from Settings at any time. Parents can do the same for their child. Deletion removes your profile, progress,
chats, notes and uploads; a minimal security log entry that an erasure happened is kept.

## Retention
Data is kept while the account is active. Security logs are kept for up to 12 months.

## Contact
**[grievance officer name and e-mail]**
"""

TERMS = f"""# Terms of use (version {_V})

1. AIVidya is a study aid. It is not a substitute for your teacher or textbook. **AI can make mistakes** - check important facts with your teacher or textbook, and use the "Report a mistake" button.
2. Use it honestly: do not use it to cheat in exams or tests, to harass anyone, or to create harmful or inappropriate content. The service filters such requests and may lock accounts.
3. Keep your password private. Anything done through your account is your responsibility. Keep access to your email address: a forgotten password is reset with a code we send there.
4. Students under 18 need a parent's or guardian's approval. Parents may withdraw it at any time.
5. Teachers may see the progress of students in their classes. Parents may see their own child's progress. Class leaderboards show only nicknames and only for students who opt in.
6. The service is provided "as is" without warranty. The operator may change or stop it, and may remove content or accounts that break these terms.
7. These terms are a template: the operator should adapt them with legal advice.
"""

PAGES = {"privacy": PRIVACY, "terms": TERMS}
