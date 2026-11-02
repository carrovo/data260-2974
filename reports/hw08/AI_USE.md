# HW8 Generative AI Use Disclosure

## 1. What did I use an AI assistant for, and what did I do myself?

I used an AI assistant to clarify the assignment, organize the implementation
into smaller stages, review code, and help interpret Kafka and Docker errors. I
ran the services and experiments locally, inspected the actual output, saved
the screenshots, confirmed the results, and managed every Git commit and push.

## 2. What AI-produced output was wrong or unsuitable?

One suggested evidence command used `docker events` to recover the Writer kill,
die, and restart events after the consumer-death experiment. On my machine the
filtered command returned no historical output, so it was not usable evidence.

## 3. How did I detect or independently verify the problem?

I saw that the `docker events` output was empty. I then checked the existing
Writer logs, Docker Compose container status, the repeated Kafka partition and
offset, and the final JSON result instead of assuming the event command had
worked.

## 4. What did I change, and why does it work now?

I used the recorded `PROCESSING STARTED` line, `Exited (137)` container status,
the same partition 1 / offset 0 after restart, and
`completed_after_restart=true` as the evidence set. Together these outputs show
that the Writer died before committing, Kafka redelivered the uncommitted
message, and processing completed after restart.
