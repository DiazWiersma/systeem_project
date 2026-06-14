Latest version (v14, March 2026) contains updated dataset including Session 80 (2025).
Previous version (v13, 19 April 2025) contained Session 79 (2024).


- The dataset now covers the United Nations General Debate Corpus (UNGDC) for the period 1946-2025.
	"UNGDC_1946-2025.tar.gz"

- There are 11,141 speeches in plain text format (UTF8). Speeches are structured by Year (Session). Each speech is named using the following convention: ISO 3166-1 alpha-3 country code, followed by the UN Session number, followed by year. E.g. USA_75_2020.txt.

- For 2025 (Session 80), the UN did not make validated PDF transcripts of General Debate statements publicly available. Accordingly, the entire Session 80 corpus was derived from audio. For each of the 190 participating states, the official simultaneous interpretation audio track was downloaded from gadebate.un.org for all six official UN languages (English, French, Spanish, Russian, Arabic, Chinese). Audio files were transcribed using the OpenAI Whisper API (model whisper-1). The English-language transcription was used as the primary text for each country. This represents a methodological change from previous sessions, where official written PDF transcripts were used as the primary source.

- For 2024 (Session 79), official transcripts of the UN General Debate with certified parallel translations into official UN languages were not yet available at the time of preparing that update. Instead, we relied on the official UN webpage for the 2024 General Debate (https://gadebate.un.org/en), which contains statements as delivered by each leader, with PDFs made available by country delegations. Most PDFs were machine-readable; however, several were image copies that required optical character recognition (OCR) processing using the Tesseract package in Python.
Statements in languages other than English were translated using the OpenAI GPT-4o model with a professional translator prompt ("You are a professional translator at the UN, translate the following statement into English..."). A random sample of translations was validated using other translation systems (Google Translate) and using text alignment. Several countries had not yet made their statements available (Turkey, Hungary, Uruguay, and Liechtenstein). For these four countries, we utilised the English language soundtrack (MP3 file) of the official simultaneous translation, first transcribing it using the ElevenLabs speech-to-text system, and then translating it into English using OpenAI GPT-4o.

- The collection also contains a file (Speakers_by_session.xlsx) recording names and posts of speakers in UN General Debates. Note: before 1994 the UN records do not consistently identify the posts of all speakers.

- Original source files contain verbatim daily transcripts of the UN General Debate (and any other business on the UN agenda on the same day). Transcripts (in PDF format) were made available by the UN Library and processed to produce the UNGD Corpus as described in the paper. The original source files (PDFs) are in several tarballs: 
	“Raw_PDFs_1946-1969.tgz”; 
	“Raw_PDFs_1970-1990.tgz”; 
	“Raw_PDFs_1991-2022.tgz”.    

- When using the UNGDC data, please cite: 

Jankin, S., Baturo, A., & Dasandi, N. (2025). Words to unite nations: The complete United Nations General Debate Corpus, 1946–present. Journal of Peace Research, 62(4), 1339-1351.

Note: for Session 80 (2025), the corpus was constructed from audio transcription rather than official written transcripts; users should be aware that transcription may introduce minor errors not present in previous sessions.

AND 

Alexander Baturo, Niheer Dasandi, and Slava Mikhaylov, "Understanding State Preferences With Text As Data: Introducing the UN General Debate Corpus" Research & Politics, 2017.