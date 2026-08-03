@regression
Feature: 50MB media limit (compress + split)

  Scenario: Small audio file is sent unchanged
    Given audio file smaller than 50 MB is downloaded
    When the bot processes the audio file
    Then the file is sent as is
    And compression is not performed
    And the user is asked about transcription

  Scenario: Audio over 50 MB is compressed to mono 96k
    Given audio file of 60 MB is downloaded
    When the bot processes the audio file
    Then the file is compressed with ffmpeg to mono 96 kbps mp3
    And the compressed file is sent

  Scenario: Audio still over 50 MB after compression is split
    Given audio file of 120 MB is downloaded
    And compression leaves the file over 50 MB
    When the bot processes the audio file
    Then the file is split into parts under 50 MB
    And each part is sent separately

  Scenario: ffmpeg unavailable — error shown, original kept
    Given compression fails because ffmpeg is unavailable
    When the bot processes the audio file
    Then the original file is kept
    And an error message is shown

  Scenario: Video over 50 MB is compressed and sent
    Given video file of 80 MB is downloaded
    When the bot processes the video file
    Then the file is compressed with ffmpeg crf28 aac96k
    And the compressed file is sent

  Scenario: Edge case — exactly 100 MB splits into 2 parts
    Given audio file of exactly 100 MB is downloaded
    When the bot processes the audio file
    Then the file is split into exactly 2 parts
    And each part is under 50 MB
