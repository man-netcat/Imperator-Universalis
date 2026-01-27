Imperator Universalis
=====================

### Imperator: Rome → Europa Universalis V Data Mapping Plan

1\. Purpose
-----------

**Imperator Universalis** is a Europa Universalis V mod that recreates Imperator: Rome’s world by converting its country, culture, and religion data into native EU5 formats.

This document defines:

* Source data locations in _Imperator: Rome_
* Target data locations in _Europa Universalis V_
* The required mapping rules
* Parsing and tooling requirements

This is a _design and implementation plan_, not AI instructions.

---

2\. Tooling & Technical Constraints
-----------------------------------

* **Parsing**

  * All Paradox script files (`.txt`) **must be parsed using `pyradox`**
  * Localisation (`.yml`) **must be parsed using a YAML parser**
* **Output Format**

  * All generated files must conform exactly to EU5’s native data structure
  * No intermediate or custom formats
* **Visual Fidelity**

  * Colours from Imperator: Rome (countries, cultures, religions) must be preserved where applicable

---

3\. Directory Structure
-----------------------

### 3.1 Imperator: Rome (Source)

**Game directory**

`/home/rick/Paradox/Games/Imperator Rome/game`

#### Countries

* Country setup:

  `setup/countries/countries.txt`
* Country data:

  `setup/main/00_default.txt`

  Relevant range:

  * Lines **4863–14515**
* Country localisation:

  `localization/english/countries_l_english.yml`

#### Cultures

* Culture groups and cultures:

  `common/cultures/*.txt`

  * One file per culture group
  * Cultures are nested within their groups
* Culture localisation:

  `localization/english/cultures_l_english.yml`

#### Religions

* Religion definitions:

  `common/religions/00_default.txt`
* Religion localisation:

  `localization/english/text_l_english.yml`

---

### 3.2 Europa Universalis V (Reference)

**Game directory**

`/home/rick/Paradox/Games/Europa Universalis V/game`

#### Countries

* Country setup files:

  `in_game/setup/countries/*.txt`
* Start data:

  `main_menu/setup/start/10_countries.txt`
* Country localisation:

  `main_menu/localization/english/country_names_l_english.yml`

#### Cultures

* Culture groups (stubs):

  `in_game/common/culture_groups/00_culture_groups.txt`
* Cultures:

  `in_game/common/cultures/*.txt`

  * Files do **not** correspond 1:1 with culture groups
  * A culture may belong to multiple culture groups
* Culture localisation:

  `main_menu/localization/english/culture_groups_l_english.yml main_menu/localization/english/cultural_and_languages_l_english.yml`

#### Religions

* Religion groups:

  `in_game/common/religion_groups/00_default.txt`
* Religions:

  `in_game/common/religions/*.txt`
* Religion localisation:

  `main_menu/localization/english/religion_l_english.yml`

---

4\. Imperator Universalis (Target Mod)
--------------------------------------

**Mod directory**

`/home/rick/Paradox/Documents/Europa Universalis V/mod/Imperator Universalis`

---

5\. Mapping Rules
-----------------

### 5.1 Countries

**Output**

`in_game/setup/countries/*.txt`

**Mapping logic**

* Read country tags from:

  * `setup/countries/`
  * `setup/main/00_default.txt`
* Combine setup and data into EU5-style country definitions
* Preserve:

  * Country tag
  * Governmental structure where possible
  * **Country colour** from Imperator: Rome
* Localisation mapped from Imperator country localisation into EU5 format

---

### 5.2 Culture Groups

**Output**

`in_game/common/culture_groups/ir_culture_groups.txt`

**Mapping logic**

* Each Imperator culture group becomes an EU5 culture group
* EU5’s stub-based culture group referencing must be respected
* Names and colours preserved where available
* Localisation written into EU5 culture group localisation files

---

### 5.3 Cultures

**Output**

`in_game/common/cultures/*.txt`

**Mapping logic**

* Each `common/cultures/*.txt` file in Imperator is parsed
* Cultures are converted into EU5-compatible culture definitions
* Cultures may be mapped to:

  * One or multiple EU5 culture groups
* Preserve:

  * Culture colour (if defined in Imperator)
* Localisation mapped to:

  * `culture_groups_l_english.yml`
  * `cultural_and_languages_l_english.yml`

---

### 5.4 Religion Groups

**Output**

`in_game/common/religion_groups/00_default.txt`

**Mapping logic**

* [ ] Use `religion_category` from Imperator:

  `common/religions/00_default.txt`
* [ ] Each Imperator religion category becomes an EU5 religion group
* [ ] Preserve names and colours where applicable
* [ ] Localisation converted to EU5 religion group localisation

---

### 5.5 Religions

**Output**

`in_game/common/religions/*.txt`

**Mapping logic**

* Each religion in Imperator is converted into an EU5 religion file
* Preserve:

  * Religion colour
  * Group association (via mapped religion group)
* EU5 religion mechanics structure must be respected
* Localisation written to:

  `religion_l_english.yml`

---

6\. Summary
-----------

This script will:

* Parse Imperator: Rome data using **pyradox**
* Parse localisation using **YAML**
* Convert countries, cultures, culture groups, religions, and religion groups
* Preserve colours and identity where possible
* Output _only_ valid EU5-format files directly into the mod directory

The result is a clean, maintainable, EU5-native conversion layer for **Imperator Universalis**.
