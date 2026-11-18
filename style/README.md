# style — how to write to each contact

One file per person the factory drafts mail to: `style/<contact>.md`, named after the first part of
their address or their first name, lowercase. `/reply` reads the file before it drafts.

Build each file from that person's real mail, not from general advice. Every line in it points to a
thread that shows it. Start it after the first five or six exchanges and update it when a draft gets
edited heavily by the owner before sending: the edit is the lesson.

## Sections each file has

    # Writing to <contact>

    ## Who they are
    Role, what they decide, what they do not want to be asked.

    ## The shape that works
    Length, order, language, greeting and sign-off. Evidence: msgids of mails that got a fast, clear reply.

    ## Canonical examples
    Two or three msgids to open and read before drafting.

    ## Banned
    Phrases and habits that cost something, each with the msgid where it did.

    ## Reply template
    The skeleton a normal status reply follows for this person.

## Defaults until a file has evidence

- Lead with what changed for them, in their words, not ours.
- One mail, one purpose. At most one question, and only after `/brief` allows it.
- Every claim about production has its command in the task file's Evidence section.
- Numbers are copied from tool output. No estimates presented as facts.
- Answer every question in their mail, or say when it will be answered.
- No internal ids (task numbers, ledger ids, mistake numbers) in client mail.
- Plain words. No apology paragraphs, no filler, no promises without a date.
