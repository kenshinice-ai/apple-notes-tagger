-- Apple 备忘录标签操作的底层动作层。
-- 每个动作都回报「光标偏移 + 选区长度 + 全文」，供上层逐字符校验。
-- 输出第一行：OK<tab>光标偏移<tab>选区长度  或  ERR<tab>原因；之后是正文全文。
-- 真标签在全文里显示为 U+FFFC (￼)。敲键前一律检查备忘录是否最前台。
on findTA()
	tell application "System Events" to tell process "Notes"
		set sg to splitter group 1 of window 1
		repeat with i from 1 to (count of scroll areas of sg)
			set sa to scroll area i of sg
			if (count of text areas of sa) > 0 then return text area 1 of sa
		end repeat
	end tell
	error "no text area"
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

on notesFront()
	tell application "System Events" to return (name of first process whose frontmost is true) is "Notes"
end notesFront

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
		if not my notesFront() then return "ERR" & tab & "frontmost is not Notes"
		set ta to my findTA()
		tell application "System Events"
			set focused of ta to true
		end tell
		delay 0.3
		tell application "System Events" to key code 125 using {command down}
		delay 0.4
		return my report(ta)
	end if

	set ta to my findTA()

	if cmd is "value" then
		return my report(ta)

	else if cmd is "tagat" then
		-- item2 = 向左移动多少次, item3 = 移动后光标应有的 UTF-16 偏移
		set nLeft to (item 2 of argv) as integer
		set expect to (item 3 of argv) as integer
		if not my notesFront() then return "ERR" & tab & "frontmost is not Notes"
		if nLeft > 0 then
			tell application "System Events"
				repeat nLeft times
					key code 123
				end repeat
			end tell
			delay 0.3
		end if
		set c to my caretOf(ta)
		if (item 1 of c) is not expect then
			return "ERR" & tab & "caret " & (item 1 of c) & " != " & expect & " (未打字)"
		end if
		if (item 2 of c) is not 0 then
			return "ERR" & tab & "有选区, 未打字"
		end if
		tell application "System Events" to keystroke " "
		delay 0.4
		tell application "System Events" to key code 51
		delay 0.4
		return my report(ta)

	else if cmd is "tagseq" then
		-- argv: tagseq p1 e1 p2 e2 ...  逐个: 左移 p 次, 校验光标 == e, 再 空格+退格
		if not my notesFront() then return "ERR" & tab & "frontmost is not Notes"
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
				return "ERR" & tab & "step " & ((k - 2) / 2 + 1) & " 有选区"
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
		if not my notesFront() then return "ERR" & tab & "frontmost is not Notes"
		tell application "System Events"
			repeat n times
				key code 51
			end repeat
		end tell
		delay 0.5
		return my report(ta)

	else if cmd is "tags" then
		-- 按文档顺序列出这条笔记里所有真标签的名字
		set out to ""
		tell application "System Events"
			repeat with e in UI elements of ta
				try
					set d to value of attribute "AXDescription" of e
					if d starts with "Tag " then set out to out & (text 5 thru -1 of d) & linefeed
				end try
			end repeat
		end tell
		return "OK" & tab & "0" & tab & "0" & linefeed & out

	else if cmd is "ret" then
		if not my notesFront() then return "ERR" & tab & "备忘录不在最前台"
		tell application "System Events" to key code 36
		delay 0.35
		return my report(ta)

	else if cmd is "space" then
		if not my notesFront() then return "ERR" & tab & "备忘录不在最前台"
		tell application "System Events" to keystroke " "
		delay 0.4
		return my report(ta)

	else if cmd is "addseq" then
		-- argv 第 2 项起是要追加的标签文本（含 #）。每个：粘贴文本 -> 敲空格触发解析。
		-- 用粘贴而不是打字，中文标签才不会被输入法吃掉。
		if not my notesFront() then return "ERR" & tab & "备忘录不在最前台"
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

	else if cmd is "left" then
		set n to (item 2 of argv) as integer
		if not my notesFront() then return "ERR" & tab & "备忘录不在最前台"
		tell application "System Events"
			repeat n times
				key code 123
			end repeat
		end tell
		delay 0.3
		return my report(ta)

	else if cmd is "undo" then
		set n to (item 2 of argv) as integer
		tell application "System Events"
			repeat n times
				keystroke "z" using {command down}
				delay 0.3
			end repeat
		end tell
		delay 0.5
		return my report(ta)
	end if
	return "ERR" & tab & "unknown cmd " & cmd
end run
