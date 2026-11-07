; Flash App installer routines, assembled with the installer that tipy-asm flash-app
; builds. installer.py calls them; arguments arrive in HL, DE, BC and results return
; in HL (see the assembly files documentation).
;
; The flash routines (port setup, unlock, lock, erase, write, find_last_app, and
; fix_relocations) are CE-Programming/app_tools' installer code, from commit
; 0fb268f179725d1727c18720343649460c72e629, whose readme permits copying its
; sources to make a custom installer. Only the entry points change: they take their
; arguments in registers instead of on CEdev's C stack, and labels are renamed for
; fasmg. The instructions that touch ports and flash are unchanged.
;
; delete_app follows the Cesium shell (BSD-3-Clause), which deletes the app at the
; address FindAppUp returns in DE and sets the flag that defragments on exit.
;
; tipy-asm flash-app replaces these placeholders: %PREFIX%, %PREFIX_LENGTH%,
; %APP_NAME%, and %PROGRAM_NAME%.

inst_prefix:
	db	%PREFIX%
inst_prefix_length := %PREFIX_LENGTH%
inst_app_name:
	db	%APP_NAME%, 0, 0, 0, 0, 0, 0, 0, 0, 0
inst_program_name:
	db	ti.ProtProgObj, %PROGRAM_NAME%, 0

; --------------------------------------------------------- C environment

; The C installer runs after CEdev's crt0, which sets these before main and
; restores them on exit. Without them, printing saves text into textShadow,
; which overwrites the flash unlock code that port_setup copies there.
; tipy: def installer_begin()
installer_begin:
	ld	iy,ti.flags
	res	1,(iy + $0D)		; no text buffer (appTextSave)
	res	3,(iy + $4A)		; use first shadow buffer
	set	5,(iy + $4C)		; only display
	ld	hl,$E00305
	ld	a,(hl)
	ld	(inst_flash_wait_states),a
	ld	(hl),h			; flash wait states 3, as crt0
	ret

; tipy: def installer_end()
installer_end:
	ld	a,(inst_flash_wait_states)
	ld	($E00305),a
	ld	iy,ti.flags
	set	1,(iy + $0D)		; use text buffer
	res	3,(iy + $4A)		; use first shadow buffer
	res	5,(iy + $4C)		; use shadow buffer
	ret
inst_flash_wait_states:
	db	3

; ---------------------------------------------------------------- port setup

; As upstream's _port_setup, then return its result (nonzero: OS not supported) in HL.
; tipy: def port_setup()
port_setup:
	push	ix
	call	inst_port_setup
	pop	ix
	ld	hl,0
	ld	l,a
	ret

inst_port_setup:
	di
	ld	hl,inst_port_reloc
	ld	bc,inst_port_reloc_size
	ld	de,ti.textShadow
	ldir
	ld	hl,($000008+5)
	ld	a,(hl)
	cp	a,$CD
	ret	nz
	inc	hl
	ld	de,(hl)
	ld	hl,(ti.CheckIfEmulated+1)
	sbc	hl,de
	ret	nz
	ld	hl,(ti.KeypadScanFull+1)
	ld	bc,10
	add	hl,bc
	push	hl
	ld	b,inst_port_pattern_size
	ld	de,inst_port_pattern
	call	ti.StrCmpre
	pop	hl
	ret	nz
	ld	(inst_unlock_target),hl
	xor	a,a
	ret

inst_port_pattern:
	db	$ED,$79,$78,$FE,$A0,$28,$01,$CF
inst_port_pattern_size := $ - inst_port_pattern

inst_port_unlock:
	push	ix
	push	de
	push	bc
	push	hl
	call	inst_unlock
	jr	inst_port_pop

inst_port_lock:
	push	ix
	push	de
	push	bc
	push	hl
	call	inst_lock
inst_port_pop:
	pop	hl
	pop	bc
	pop	de
	pop	ix
	ret

; Copied to textShadow by inst_port_setup and run from there.
inst_port_reloc:
inst_unlock := ti.textShadow
	call	ti._frameset0
	ld	iy,inst_unlock_finish
	ld	sp,ti._indcall + 7
	ld	bc,$22
	xor	a,a
inst_unlock_target := ti.textShadow + (($ + 1) - inst_port_reloc)
	jp	0
inst_unlock_finish := ti.textShadow + ($ - inst_port_reloc)
	ld	sp,ix
	pop	ix
	ld	a,$8C
	out0	($24),a
	in0	a,($06)
	or	a,4
	out0	($06),a
	ret
inst_lock := ti.textShadow + ($ - inst_port_reloc)
	xor	a,a
	out0	($28),a
	in0	a,($06)
	res	2,a
	out0	($06),a
	ld	a,$88
	out0	($24),a
	ld	a,$D1
	out0	($22),a
	ret
inst_port_reloc_size := $ - inst_port_reloc

; --------------------------------------------------------------------- flash

; flash_erase and flash_write push their arguments and call upstream's routines
; unchanged, so those routines see the same C stack frame (IX) they were written for.

; tipy: def flash_erase(page)
flash_erase:
	push	hl			; uint8_t page, as C passes it
	call	inst_flash_erase
	pop	hl
	ret

; tipy: def flash_write(source, destination, length)
flash_write:
	push	bc			; size_t len
	push	hl			; const void *src
	push	de			; void *dst
	call	inst_flash_write
	pop	de
	pop	hl
	pop	bc
	ret

; Write a 24-bit value, as the C installer writes &app_size.
; tipy: def flash_write_size(destination, value)
flash_write_size:
	ld	(inst_size_buffer),de
	ex	de,hl
	ld	hl,inst_size_buffer
	ld	bc,3
	jr	flash_write
inst_size_buffer:
	db	0,0,0

; Upstream's _flash_erase and _flash_write, unchanged apart from labels.
inst_flash_erase:
	ld	iy,$d00080
	push	ix
	ld	ix,0
	add	ix,sp
	call	inst_port_unlock
	ld	a,(ix+6)
	call	inst_erase_wrap
	call	inst_port_lock
	pop	ix
	ret
inst_erase_wrap:
	ld	bc,$f8
	push	bc
	jp	$02dc

inst_flash_write:
	ld	iy,$d00080
	push	ix
	ld	ix,0
	add	ix,sp
	ld	de,(ix+6)
	ld	hl,(ix+9)
	ld	bc,(ix+12)
	call	inst_port_unlock
	call	$02e0
	call	inst_port_lock
	pop	ix
	ret

; -------------------------------------------------------------- applications

; tipy: def find_last_app()
find_last_app:
	ld	hl,$3b0000		; applications start here
inst_find_next_app:
	push	hl
	call	$22044			; locates start of next application header
	pop	de
	jr	nz,inst_find_next_app
	ex	de,hl
	ret

; tipy: def fix_relocations(app)
fix_relocations:
	push	hl			; void *app
	call	inst_fix_relocations
	pop	hl
	ret

; Upstream's _fix_relocations, unchanged apart from labels.
inst_fix_relocations:
	push	ix
	ld	ix,0
	add	ix,sp
	ld	hl,(ix+6)

	push	hl
	ld	de,$112
	add	hl,de
	ld	hl,(hl)			; hl = code offset
	ld	de,$100
	add	hl,de
	pop	de
	add	hl,de
	ex	de,hl			; de = code section start

	ld	bc,$12a
	add	hl,bc			; hl = relocation table start
inst_relocate:
	or	a,a
	sbc	hl,de
	add	hl,de
	jr	z,inst_relocate_done

	ld	ix,(hl)
	add	ix,de			; location to overwrite
	inc	hl
	inc	hl
	inc	hl			; hl points to value | base
	push	hl
	push	de
	ld	hl,(hl)

	ld	bc,$800000		; check if data or code relative
	or	a,a
	sbc	hl,bc
	add	hl,bc
	jr	c,inst_code_relative
	ld	de,$d1787c - $800000
inst_code_relative:
	add	hl,de
	lea	de,ix + 0
	ld	($d02655),hl		; use tempFreeArc since it is spare ram
	ld	hl,$d02655
	ld	bc,3
	ld	iy,$d00080
	call	inst_port_unlock
	call	$02e0
	call	inst_port_lock
	pop	de
	pop	hl
	inc	hl
	inc	hl
	inc	hl
	jr	inst_relocate
inst_relocate_done:
	xor	a,a
	pop	ix
	ret

; The app's name, baked in when the installer is built.
; tipy: def app_name()
app_name:
	ld	hl,inst_app_name
	ret

; Copy the 8-character name field at HL into a buffer that always ends in zero.
; tipy: def copy_app_name(source)
copy_app_name:
	ld	de,inst_name_buffer
	ld	bc,8
	ldir
	ld	hl,inst_name_buffer
	ret
inst_name_buffer:
	db	0,0,0,0,0,0,0,0,0,0

; Returns 1 if the app named at HL is installed, 0 if not. This walks the apps
; with FindAppUp, as the apps menu and Cesium do. A deleted app stays in flash until
; the archive is cleaned up, and os.FindAppStart still finds it; FindAppUp does not.
; tipy: def app_installed(name)
app_installed:
	call	inst_find_app
	ld	hl,0
	ret	c
	inc	hl
	ret

; Delete the installed app named at HL. Returns 1 if deleted, 0 if not found.
; tipy: def delete_app(name)
delete_app:
	call	inst_find_app
	ld	hl,0
	ret	c
	push	ix
	ex	de,hl			; the app's address, as Cesium passes it
	call	ti.DeleteApp
	pop	ix
	ld	iy,ti.flags
	set	3,(iy + $25)		; defragment the archive on exit
	ld	hl,1
	ret

; Find the app named at HL. Returns carry set if it is not installed; otherwise
; carry clear and DE = the app's address from FindAppUp.
inst_find_app:
	ld	(inst_delete_name),hl
	push	ix
	call	ti.ZeroOP3
	ld	a,ti.AppObj
	ld	(ti.OP3),a
inst_find_next:
	call	ti.OP3ToOP1
	call	ti.FindAppUp
	push	hl
	push	de
	call	ti.OP1ToOP3
	pop	de
	pop	hl
	jr	c,inst_find_done	; no more apps
	ld	hl,(inst_delete_name)
	ld	ix,ti.OP1 + 1
	ld	b,8
inst_find_compare:
	ld	a,(hl)
	cp	a,(ix)
	jr	nz,inst_find_next
	or	a,a
	jr	z,inst_find_found	; both names ended together
	inc	hl
	inc	ix
	djnz	inst_find_compare
inst_find_found:
	or	a,a			; carry clear: found
inst_find_done:
	pop	ix
	ld	iy,ti.flags
	ret
inst_delete_name:
	db	0,0,0

; ------------------------------------------------------------------ AppVars

; Put the name of AppVar number HL (prefix + decimal index) in OP1. Returns its length.
inst_set_appvar_name:
	ld	de,ti.OP1
	ld	a,ti.AppVarObj
	ld	(de),a
	inc	de
	push	hl
	ld	hl,inst_prefix
	ld	bc,inst_prefix_length
	ldir
	pop	hl
	ld	a,l
	ld	c,inst_prefix_length
	cp	a,10
	jr	c,inst_one_digit
	ld	b,'0'
inst_tens:
	sub	a,10
	inc	b
	cp	a,10
	jr	nc,inst_tens
	ex	de,hl
	ld	(hl),b
	ex	de,hl
	inc	de
	inc	c
inst_one_digit:
	add	a,'0'
	ld	(de),a
	inc	de
	inc	c
	xor	a,a
	ld	(de),a
	ld	a,c
	ret

; Returns the address of AppVar number HL's size word, or 0 if it does not exist.
; tipy: def appvar_data(index)
appvar_data:
	call	inst_set_appvar_name
	ld	(inst_name_length),a
	call	ti.ChkFindSym
	jr	c,inst_appvar_missing
	ld	(inst_found),de
	ld	a,(inst_found + 2)
	cp	a,$d0
	ex	de,hl
	ld	iy,ti.flags
	ret	nc			; in RAM: the size word is first
	ld	de,0			; archived: skip the 10-byte header and the name
	ld	a,(inst_name_length)
	ld	e,a
	add	hl,de
	ld	de,10
	add	hl,de
	ret
inst_appvar_missing:
	ld	iy,ti.flags
	ld	hl,0
	ret
inst_found:
	db	0,0,0
inst_name_length:
	db	0

; tipy: def delete_appvar(index)
delete_appvar:
	call	inst_set_appvar_name
	call	ti.ChkFindSym
	ld	iy,ti.flags
	ret	c
	call	ti.DelVarArc
	ld	iy,ti.flags
	ret

; tipy: def delete_installer()
delete_installer:
	ld	hl,inst_program_name
	call	ti.Mov9ToOP1
	call	ti.ChkFindSym
	ld	iy,ti.flags
	ret	c
	call	ti.DelVarArc
	ld	iy,ti.flags
	ret

; ----------------------------------------------------------- variable table

; tipy: def vat_start()
vat_start:
	push	ix
	call	ti.os.GetSymTablePtr
	pop	ix
	ld	iy,ti.flags
	ret

; Advance to the next variable; returns 0 after the last one. vat_data,
; vat_name_length, and vat_name_char then describe it.
; tipy: def vat_next(entry)
vat_next:
	push	ix
	ld	de,inst_vat_data
	push	de
	ld	de,inst_vat_name
	push	de
	ld	de,inst_vat_length
	push	de
	ld	de,inst_vat_type
	push	de
	push	hl
	call	ti.os.NextSymEntry
	pop	bc
	pop	bc
	pop	bc
	pop	bc
	pop	bc
	pop	ix
	ld	iy,ti.flags
	ret

; tipy: def vat_data()
vat_data:
	ld	hl,(inst_vat_data)
	ret

; tipy: def vat_name_length()
vat_name_length:
	ld	hl,(inst_vat_length)
	ret

; tipy: def vat_name_char(index)
vat_name_char:
	ld	de,inst_vat_name
	add	hl,de
	ld	a,(hl)
	ld	hl,0
	ld	l,a
	ret

inst_vat_data:
	db	0,0,0
inst_vat_type:
	db	0,0,0
inst_vat_length:
	db	0,0,0
inst_vat_name:
	db	0,0,0,0,0,0,0,0,0,0

; ------------------------------------------------------------------- misc

; tipy: def peek16(address)
peek16:
	ld	de,0
	ld	e,(hl)
	inc	hl
	ld	d,(hl)
	ex	de,hl
	ret

; tipy: def put_str(text)
put_str:
	call	ti.PutS
	ld	iy,ti.flags
	ret

; tipy: def clear_home()
clear_home:
	call	ti.ClrScrn
	call	ti.HomeUp
	ld	iy,ti.flags
	ret
