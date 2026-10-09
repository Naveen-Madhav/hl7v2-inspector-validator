# Validation rules and coverage

Definition: **HL7v2-IV-1.0**. This validator supports HL7 v2.5.1 admission and patient laboratory scenarios. It does not certify complete HL7 conformance or clinical correctness.

The profiles expect these core sequences:

| Scenario | Core sequence |
| --- | --- |
| ADT-A01 admission | MSH, EVN, PID, PV1 |
| ORM-O01 patient laboratory order | MSH, PID, ORC, OBR; repeat ORC/OBR groups |
| ORU-R01 patient laboratory result | MSH, PID, OBR, OBX; repeat observations and OBR/OBX groups |

The patient laboratory profiles deliberately require PID and laboratory observation segments. Those requirements do not apply to every possible ORM or ORU message. Additional segments remain inspectable, but produce a limited-coverage notice. Multi-patient messages are outside the implemented grammar.

| Rule | Check | Severity and basis |
| --- | --- | --- |
| R01 | One leading MSH; one unframed message within 5 MB, 1,000 segments, and 20,000 separator characters; reject disallowed control characters | Error. Input boundary and header structure |
| R02 | MSH-1 and MSH-2 declare five distinct ASCII punctuation separators | Error. ER7 encoding; bounded v2.5.1 profile |
| R03 | MSH-9 contains message code, event, and consistent structure | Error. Selected project profile |
| R04 | MSH-12 declares a version | Error when absent. Versions other than 2.5.1 receive limited coverage |
| R05 | MSH-10 contains a control ID | Error. HL7 v2.5.1 |
| R06 | MSH-11.1 is P, D, or T | Error. HL7 processing code |
| R07 | Required core segments exist, including an OBR per laboratory order and an OBX per result group | Error. Selected project profile |
| R08 | Core segment order and group boundaries; declared field separator; balanced escape delimiters in core fields | Error. Project grammar and ER7 encoding |
| R09 | MSH-7, EVN-2, and PV1-2 are usable when their segments occur | Error. Selected required fields |
| R10 | PID-3 has an identifier, including the first component of each populated repetition | Error. Patient scenario requirement |
| R11 | PID-5 contains a usable name component | Error. Patient scenario requirement; Unicode and single-component names accepted |
| R12 | Selected timestamps have valid precision, calendar values, fractions, and numeric offsets | Error. HL7 date/time syntax |
| R13 | ORC-1 and OBR-4 are usable; corresponding populated ORC/OBR order identifiers agree | Error for missing values. Identifier disagreement is a project advisory warning |
| R14 | OBX-2 is usable except deletion status D; OBX-5 fits NM, ST, TX, CE, or CWE | Error for contradictions. Code without coding system is an advisory warning; other datatypes receive limited coverage |
| R15 | OBX-3 identifies the observation; OBX-11 is a recognized status; value is usable where the status requires it | Error. Selected result requirements and HL7 status codes |

Date/time fields checked: MSH-7; EVN-2/6; PID-7; PV1-44/45; ORC-9; OBR-7/8/22; OBX-14/19. Reduced precision is accepted. Fractional seconds require second precision and at most four digits. Offsets are limited to ±1400. This bounded policy is not a timestamp conversion service. Explicit null (`""`) and empty fields are displayed separately; neither satisfies a required value.

Numeric checks permit signs, decimals, and leading decimal points, but not scientific notation. ST/TX separators must be escaped. CE/CWE checks enforce component limits and flag a missing coding system when a code is present. They do not validate terminology membership. OBX-11 accepts C, D, F, I, N, O, P, R, S, U, W, X. D, I, N, O, U, and X can omit the value in this implementation. D can also omit OBX-2.

No blanket pass is reported when parsing fails, a version/type is unsupported, extra segments fall outside coverage, or an OBX datatype is unimplemented. Raw inspection can still show recoverable fields. Escapes stay encoded; matching every escape code is outside scope. Processing ID T marks synthetic training fixtures but the app does not infer that an uploaded message is synthetic.

## Sources and implementation decisions

- [hl7apy parser API](https://hl7apy.readthedocs.io/en/latest/api_docs/parser.html): tolerant ER7 parsing and `find_groups=False` support flat segment inspection. Tolerance is not conformance validation.
- [hl7apy validation API](https://hl7apy.readthedocs.io/en/latest/api_docs/validation.html): distinguishes library validation from parsing. The application reports its own selected rule families rather than claiming that complete library validation ran.
- [hl7apy v2.5.1 message definitions](https://github.com/crs4/hl7apy/blob/master/hl7apy/v2_5_1/messages.py) and [group definitions](https://github.com/crs4/hl7apy/blob/master/hl7apy/v2_5_1/groups.py): references for message structure. The project's laboratory profiles intentionally narrow those structures.
- [CDC HL7 v2.5.1 implementation guide](https://www.cdc.gov/vaccines/programs/iis/technical-guidance/downloads/hl7guide-2011-02.pdf): printed page 27 discusses absent and explicit-null values; pages 45–46 describe DT and DTM. Immunization-specific requirements are not applied to these laboratory profiles.
- [HL7 OBX-to-Observation mapping](https://hl7.org/fhir/uv/v2mappings/ConceptMap-segment-obx-to-observation.html): corroborates the relationship between OBX-2 and the value representation. It is a mapping guide, not a replacement for a sender's v2 specification.

Reviewed October 9, 2026. Field names and datatypes in the inspector come from the installed hl7apy version. The application does not reproduce the complete licensed HL7 standard.
