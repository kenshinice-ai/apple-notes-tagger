-- Apple Notes tagging primitives.
-- Every action reports "OK<tab>caret<tab>selectionLength" (or "ERR<tab>reason")
-- followed by the note's full text, so the caller can verify it character by
-- character. A real tag appears in that text as U+FFFC.
--
-- Nothing here matches on localised UI strings: the Notes process is located by
-- bundle identifier, and inline elements are handed to the caller as raw
-- role/subrole/description triples for it to interpret.

on notesProc()
	tell application "System Events"
		try
			return first application process whose bundle identifier is "com.apple.Notes"
		on error
			error "Notes is not running"
		end try
	end tell
end notesProc

on notesFront()
	tell application "System Events"
		try
			return (bundle identifier of (first application process whose frontmost is true)) is "com.apple.Notes"
		on error
			return false
		end try
	end tell
end notesFront

-- Focus gets stolen (the user types, a notification lands). Rather than failing
-- the whole batch, take it back once and re-check before pressing any key.
on ensureFront()
	if my notesFront() then return true
	tell application "Notes" to activate
	delay 0.6
	return my notesFront()
end ensureFront

on findTA()
	tell application "System Events" to tell (my notesProc())
		set sg to splitter group 1 of window 1
		repeat with i from 1 to (count of scroll areas of sg)
			set sa to scroll area i of sg
			if (count of text areas of sa) > 0 then return text area 1 of sa
		end repeat
	end tell
	error "no text area in the Notes window"
end findTA

on caretOf(ta)
	tell application "System Events"
		set r to value of attribute "AXSelectedTextRange" of ta
		return {(item 1 of r) - 1, (item 2 of r) - ((item 1 of r) - 1)}
	end tell
end caretOf

on report(ta)
	set c to my caretOf(ta)
	tell application "System Events" to set v to value of attribute "AXValue" of ta
	return "OK" & tab & (item 1 of c) & tab & (item 2 of c) & linefeed & v
end report

on run argv
	set cmd to item 1 of argv

	if cmd is "open" then
		set nid to item 2 of argv
		try
			tell application "Notes"
				activate
				show note id nid
			end tell
		on error e
			return "ERR" & tab & "show failed: " & e
		end try
		delay 0.9
		if not my ensureFront() then return "ERR" & tab & "Notes is not frontmost"
		set ta to my findTA()
		tell application "System Events" to set focused of ta to true
		delay 0.3
		tell application "System Events" to key code 125 using {command down}
		delay 0.4
		return my report(ta)
	end if

	set ta to my findTA()

	if cmd is "value" then
		return my report(ta)

	else if cmd is "elements" then
		-- One line per inline element, in document order, matching the U+FFFC
		-- placeholders in the note text one for one:
		--     role <tab> subrole <tab> description
		-- Tags are AXUnknown with no subrole; attachments are AXLink with subrole
		-- AXTextAttachment. The description is localised ("Tag foo" in English),
		-- so the caller decides how to read it.
		set out to ""
		tell application "System Events"
			repeat with e in UI elements of ta
				set r to ""
				set sr to ""
				set d to ""
				try
					set r to role of e
				end try
				try
					set sr to value of attribute "AXSubrole" of e
				end try
				try
					set d to value of attribute "AXDescription" of e
				end try
				set out to out & r & tab & sr & tab & d & linefeed
			end repeat
		end tell
		return "OK" & tab & "0" & tab & "0" & linefeed & out

	else if cmd is "left" then
		set n to (item 2 of argv) as integer
		if not my ensureFront() then return "ERR" & tab & "Notes is not frontmost"
		tell application "System Events"
			repeat n times
				key code 123
			end repeat
		end tell
		delay 0.3
		return my report(ta)

	else if cmd is "tagseq" then
		-- argv: tagseq p1 e1 p2 e2 …
		-- For each pair: move left p times, verify the caret sits at exactly UTF-16
		-- offset e — and if it does not, return without pressing a single key —
		-- then space (fires the parser) and backspace (removes the space).
		if not my ensureFront() then return "ERR" & tab & "Notes is not frontmost"
		set nArgs to (count of argv)
		set k to 2
		repeat while k < nArgs
			set nLeft to (item k of argv) as integer
			set expect to (item (k + 1) of argv) as integer
			if nLeft > 0 then
				tell application "System Events"
					repeat nLeft times
						key code 123
					end repeat
				end tell
				delay 0.25
			end if
			set c to my caretOf(ta)
			if (item 1 of c) is not expect then
				return "ERR" & tab & "step " & ((k - 2) / 2 + 1) & " caret " & (item 1 of c) & " != " & expect
			end if
			if (item 2 of c) is not 0 then
				return "ERR" & tab & "step " & ((k - 2) / 2 + 1) & " has a selection"
			end if
			tell application "System Events" to keystroke " "
			delay 0.4
			tell application "System Events" to key code 51
			delay 0.35
			set k to k + 2
		end repeat
		return my report(ta)

	else if cmd is "back" then
		set n to (item 2 of argv) as integer
		if not my ensureFront() then return "ERR" & tab & "Notes is not frontmost"
		tell application "System Events"
			repeat n times
				key code 51
			end repeat
		end tell
		delay 0.5
		return my report(ta)

	else if cmd is "ret" then
		if not my ensureFront() then return "ERR" & tab & "Notes is not frontmost"
		tell application "System Events" to key code 36
		delay 0.35
		return my report(ta)

	else if cmd is "space" then
		if not my ensureFront() then return "ERR" & tab & "Notes is not frontmost"
		tell application "System Events" to keystroke " "
		delay 0.4
		return my report(ta)

	else if cmd is "addseq" then
		-- argv from item 2 on: the tag texts to append, each including its '#'.
		-- Paste rather than type: the clipboard bypasses the input method, which
		-- would otherwise mangle non-ASCII tags. The space fires the parser.
		if not my ensureFront() then return "ERR" & tab & "Notes is not frontmost"
		repeat with k from 2 to (count of argv)
			set t to item k of argv
			set the clipboard to t
			delay 0.25
			tell application "System Events" to keystroke "v" using {command down}
			delay 0.5
			tell application "System Events" to keystroke " "
			delay 0.5
		end repeat
		return my report(ta)

	else if cmd is "undo" then
		set n to (item 2 of argv) as integer
		if not my ensureFront() then return "ERR" & tab & "Notes is not frontmost"
		tell application "System Events"
			repeat n times
				keystroke "z" using {command down}
				delay 0.3
			end repeat
		end tell
		delay 0.5
		return my report(ta)
	end if
	return "ERR" & tab & "unknown command " & cmd
end run
