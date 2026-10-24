"""Unit tests for cleaning and segmentation rules (no PDFs, no subprocesses)."""
from bidwit.parts.extract.clean import Line, clean_pages, join_lines, normalize
from bidwit.parts.extract.segment import MAX_CLAUSE_CHARS, plausible_next, segment


def L(text, page=1, top=100.0, bold=False):
    return Line(page=page, text=text, bold=bold, x0=50.0, top=top)


def test_normalize_ligatures_controls_and_spaces():
    assert normalize("of" + chr(0xFB01) + "ce  space" + chr(0x200B) + chr(0x202E)) == "office space"
    assert normalize("con" + chr(0xAD)) == "con-"


def test_join_lines_repairs_hyphenated_words_only():
    assert join_lines(["provide con-", "solidated reports"]) == "provide consolidated reports"
    assert join_lines(["AES-", "256"]) == "AES- 256"                 # not a lowercase word split: kept


def test_plausible_next():
    assert plausible_next(None, (1, 1))
    assert plausible_next((2, 1), (2, 2)) and plausible_next((2, 1), (2, 1, 1)) and plausible_next((2, 1, 2), (2, 2))
    assert plausible_next((3, 1), (5, 1))                            # skipped section allowed
    assert not plausible_next((2, 1), (99, 982))                     # '99.982 percent' is not a clause
    assert not plausible_next((2, 5), (2, 3))                        # going backwards
    assert not plausible_next((2, 1), (2, 40))                       # implausible jump


def test_number_at_line_start_stays_inside_the_clause():
    out = segment([L("2.1 Uptime shall be at least"), L("99.982 percent measured monthly.")], [])
    assert len(out) == 1 and out[0]["text"] == "Uptime shall be at least 99.982 percent measured monthly."


def test_text_before_first_clause_is_kept_as_paragraph():
    out = segment([L("Notice inviting tender"), L("1.1 Bids shall be submitted online.")], [])
    assert out[0]["kind"] == "paragraph" and out[0]["text"] == "Notice inviting tender"


def test_sub_item_without_parent_is_not_dropped():
    out = segment([L("(a) a stray item")], [])
    assert (out[0]["kind"], out[0]["clause_no"], out[0]["text"], out[0]["parent_key"]) == ("sub_item", "(a)", "a stray item", None)


def test_long_clause_is_split_never_cut():
    long = "word " * 3000
    out = segment([L("1.1 " + long)], [])
    assert len(out) >= 2 and "".join(o["text"] for o in out).replace(" ", "") == long.replace(" ", "")
    assert all(len(o["text"]) <= MAX_CLAUSE_CHARS for o in out)


def test_annexure_heading_starts_new_section_and_restarts_numbering():
    out = segment([L("1.2 Last clause."), L("Annexure 2: Bank Guarantee Format"), L("1.1 The bank shall pay.")], [])
    assert [o["kind"] for o in out] == ["clause", "heading", "clause"]
    assert out[2]["section"] == "Annexure 2: Bank Guarantee Format" and out[2]["clause_no"] == "1.1"


def test_tables_land_in_reading_order():
    t = {"page": 1, "top": 150.0, "rows": [["S.No", "Criteria"], ["1", "Must hold ISO 27001"]]}
    out = segment([L("3 Pre-Qualification", top=100, bold=True), L("3.1 After the table.", top=300)], [t])
    assert [o["kind"] for o in out] == ["heading", "table_header", "table_row", "clause"]
    assert out[1]["text"] == "S.No | Criteria"                         # header row kept as a unit
    assert out[2]["text"] == "S.No: 1 | Criteria: Must hold ISO 27001"


def test_headers_footers_removed_only_in_page_edges():
    pages = [{"page": i, "height": 800.0, "lines": [
        {"text": "RFP 12 Header", "top": 10, "bottom": 20, "bold": False, "x0": 0},
        {"text": "RFP 12 Header", "top": 400, "bottom": 410, "bold": False, "x0": 0},   # same text mid-page: kept
        {"text": f"Page {i} of 4", "top": 780, "bottom": 790, "bold": False, "x0": 0}]} for i in range(1, 5)]
    body, removed = clean_pages(pages)
    assert [b.text for b in body] == ["RFP 12 Header"] * 4
    assert "RFP 12 Header" in removed and "Page 1 of 4" in removed


def test_heading_is_kept_even_with_nothing_under_it():
    out = segment([L("1.1 First."), L("4 Commercial Terms", bold=True), L("5 General", bold=True)], [])
    assert [(o["kind"], o["text"]) for o in out][1:] == [("heading", "Commercial Terms"), ("heading", "General")]


def test_text_after_heading_is_not_glued_to_the_heading():
    out = segment([L("2 Scope of Work", bold=True), L("Unnumbered intro sentence.")], [])
    assert [o["kind"] for o in out] == ["heading", "paragraph"]


def test_more_numbering_styles():
    out = segment([L("1.g.3. Scope."), L("1.g.4. Coordinate circuit installation;"), L("l. The bidder has to perform warranty;"),
                   L("A) Upper-case item"), L("2) Bracket number item"), L("1. A numbered list item that is a full sentence."),
                   L(chr(0xF0B7) + " Private-use bullet glyph"), L(chr(0x2022) + " Normal bullet"), L("- dash bullet")], [])
    assert [(o["kind"], o["clause_no"]) for o in out] == [
        ("clause", "1.g.3"), ("clause", "1.g.4"), ("sub_item", "l."), ("sub_item", "A)"), ("sub_item", "2)"),
        ("sub_item", "1"), ("sub_item", "-"), ("sub_item", "-"), ("sub_item", "-")]
    assert out[6]["text"] == "Private-use bullet glyph"


def test_not_items():
    out = segment([L("1.1 The bidder shall, e.g."), L("e.g. this is a continuation"), L("-2026 numbers are not bullets"), L("No. 5 is not an item")], [])
    assert len(out) == 1


def test_split_long_cuts_at_sentence_end():
    text = ("This is a sentence. " * 400).strip()
    parts = __import__("bidwit.parts.extract.segment", fromlist=["split_long"]).split_long(text, 1000)
    assert all(p.endswith(".") for p in parts) and " ".join(parts) == text


def test_table_continuing_on_new_page_reuses_header():
    t1 = {"page": 1, "top": 100.0, "rows": [["S.No", "Criteria", "Documents"], ["1", "Must hold ISO 27001.", "Certificate copy"]]}
    t2 = {"page": 2, "top": 50.0, "rows": [["5", "Must not be blacklisted.", "Self-declaration"]]}
    out = segment([], [t1, t2])
    assert out[-1]["text"] == "S.No: 5 | Criteria: Must not be blacklisted. | Documents: Self-declaration"


def test_data_row_is_never_used_as_header():
    t = {"page": 1, "top": 50.0, "rows": [["5", "Bidder should not be blacklisted.", "Self-declaration"], ["6", "Must hold ISO.", "Copy"]]}
    out = segment([], [t])
    assert [o["text"] for o in out] == ["5 | Bidder should not be blacklisted. | Self-declaration", "6 | Must hold ISO. | Copy"]


def test_blank_line_gap_starts_a_new_paragraph_under_the_same_clause():
    out = segment([L("1.1 First line of clause", top=100), L("continues here.", top=114),
                   L("Invitation for bids: a new paragraph after a blank line.", top=150), L("and its second line.", top=164)], [])
    assert [(o["kind"], o["parent_key"]) for o in out] == [("clause", None), ("paragraph", 0)]
    assert out[1]["text"] == "Invitation for bids: a new paragraph after a blank line. and its second line."


def test_dotted_serial_or_flag_cells_never_make_a_header():
    t = {"page": 1, "top": 50.0, "rows": [["6.2", "Detect malicious activities performed by users", "M"],
                                         ["6.3", "Collect user data from directory services", "M"]]}
    out = segment([], [t])
    assert [o["text"] for o in out] == ["6.2 | Detect malicious activities performed by users | M",
                                        "6.3 | Collect user data from directory services | M"]


def test_sentences_starting_with_part_form_schedule_are_not_headings():
    out = segment([L("1.1 Clause one."), L("part of the equipment or service gives problem, an event"),
                   L("form, by its officials by following transparent procedures."), L("Schedule Implemented by Percentage")], [])
    assert [o["kind"] for o in out] == ["clause"] and out[0]["section"] is None


def test_annex_headings_with_identifiers():
    for t in ["ANNEXURE " + chr(0x2013) + " 8 " + chr(0x2013) + " Link Details", "Section III", "Part B - Scope", "Form 3"]:
        out = segment([L(t)], [])
        assert out[0]["kind"] == "heading" and out[0]["section"] == t, t


def test_bold_title_sets_section_without_restarting_numbering():
    out = segment([L("1.1 First."), L("ELIGIBILITY CRITERIA (Documents to be Submitted Online)", bold=True),
                   L("1.2 Second clause."), L("Note:", bold=True), L("continues.")], [])
    assert [o["kind"] for o in out] == ["clause", "heading", "clause"]
    assert out[2]["section"] == "ELIGIBILITY CRITERIA (Documents to be Submitted Online)" and out[2]["clause_no"] == "1.2"
    assert out[2]["text"] == "Second clause. Note: continues."           # 'Note:' is a label, not a title


def test_bold_sentence_is_not_a_title():
    out = segment([L("1.1 First."), L("Bids must reach us before the deadline.", bold=True)], [])
    assert [o["kind"] for o in out] == ["clause"]


def test_header_only_carries_to_a_direct_continuation():
    t1 = {"page": 1, "top": 100.0, "rows": [["Event", "Criticality", "Timeframe"], ["Link down", "High", "15 min"]]}
    t_far = {"page": 9, "top": 50.0, "rows": [["1", "Project Manager", "CCNP"]]}
    out = segment([], [t1, t_far])
    assert out[-1]["text"] == "1 | Project Manager | CCNP"          # same width, different table: no borrowed names
    t_next = {"page": 2, "top": 50.0, "rows": [["Power fail", "Medium", "30 min"]]}
    out = segment([], [t1, t_next])
    assert out[-1]["text"] == "Event: Power fail | Criticality: Medium | Timeframe: 30 min"


def test_text_between_tables_breaks_the_continuation():
    t1 = {"page": 1, "top": 100.0, "rows": [["Event", "Criticality"], ["Link down", "High"]]}
    t2 = {"page": 2, "top": 300.0, "rows": [["Power fail", "Medium"]]}
    out = segment([L("A paragraph between the two tables.", page=2, top=100.0)], [t1, t2])
    assert out[-1]["text"] == "Power fail | Medium"


def test_short_data_rows_after_the_header_are_data_not_headers():
    t = {"page": 1, "top": 100.0, "rows": [["Severity", "Response", "Resolution"], ["Severity 1", "30 minutes", "4 hours"],
                                          ["Severity 2", "1 hour", "8 hours"]]}
    out = segment([], [t])
    assert [o["kind"] for o in out] == ["table_header", "table_row", "table_row"]
    assert out[1]["text"] == "Severity: Severity 1 | Response: 30 minutes | Resolution: 4 hours"


def test_repeated_header_on_continuation_page_is_recognised():
    t1 = {"page": 1, "top": 100.0, "rows": [["Event", "Criticality"], ["Link down", "High"]]}
    t2 = {"page": 2, "top": 50.0, "rows": [["Event", "Criticality"], ["Power fail", "Medium"]]}
    out = segment([], [t1, t2])
    assert [o["kind"] for o in out] == ["table_header", "table_row", "table_header", "table_row"]
    assert out[-1]["text"] == "Event: Power fail | Criticality: Medium"


def test_abbreviated_header_and_lettered_sub_headers():
    t = {"page": 1, "top": 50.0, "rows": [["SI.", "Criteria", "Documents to be submitted by Bidder"],
                                         ["1", "Bidder must be registered in India.", "Certificate"],
                                         ["(B)", "Criteria", "Documents to be submitted by successful bidder"],
                                         ["1", "Resources must be on payroll.", "Payslips"]]}
    out = segment([], [t])
    assert [o["kind"] for o in out] == ["table_header", "table_row", "table_header", "table_row"]
    assert out[1]["text"].startswith("SI.: 1 | Criteria: Bidder must")
    assert out[3]["text"] == "(B): 1 | Criteria: Resources must be on payroll. | Documents to be submitted by successful bidder: Payslips"
