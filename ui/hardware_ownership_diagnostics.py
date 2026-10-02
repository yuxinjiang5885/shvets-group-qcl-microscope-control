"""Read-only Python/Qt ownership snapshot. Never queries instrument state."""


def hardware_ownership_snapshot(window):
    bridge = window.localization_bridge
    controller = bridge.controller
    with controller.registration.lock:
        # blockers() inspects cached state and Qt worker lifecycle only. Do not
        # call bridge.refresh(): it updates the ownership activity registry.
        blockers = list(bridge.blockers())
        ledger = bridge.legacy_daq_evidence.snapshot()
        pending = [r['source'] for r in ledger['transitions'] if not r['released']]
        completed=[r for r in ledger['transitions'] if r['released']]
        # Match InputHandoff.prepare's pre-handoff gate. These two conditions
        # are handled by handoff, not ignored by the acquisition workflow.
        handoff_managed = ('gamepad_handoff_required', 'hardware_joystick_disable_unconfirmed')
        pre_handoff = [r for r in blockers if r not in handoff_managed]
        launch = []
        runner = getattr(window, 'h_only_runner', None)
        if runner is not None and runner.busy:
            launch.append('H_run_already_active')
        if not getattr(window, 'translation_launch_enabled', False):
            launch.append('translation_live_launch_requires_supervised_opt_in')
        ownership = controller.ownership.can_begin_localization()
        reasons = list(dict.fromkeys(launch + pre_handoff + list(ownership.reasons)))
        controls = getattr(window, 'h_only_controls', None)
        last_message = controls.result.text() if controls is not None else None
        handle = controller.active
        objective_flags = {name: getattr(window, name, False) for name in
            ('objective_motion_active', 'objective_daq_active', 'objective_ownership_uncertain')}
        objective_flags['widget_exists'] = getattr(window, 'pi_scanner_widget', None) is not None
        objective_flags['state'] = ('blocked_or_unconfirmed' if
            any(value is not False for value in objective_flags.values()) else 'no_owner_reported')
        autofocus = getattr(window, 'autofocus_active', False)
        widget = getattr(window, 'pi_scanner_widget', None)
        owner = bridge.objective_owner
        if owner is not None:
            objective_flags.update(owner.snapshot())
            objective_flags['managed'] = bridge.managed_objective(widget)
            objective_flags['snake_parent_reserved'] = bridge.snake_parent is not None
            if widget is not None and not objective_flags['managed']:
                objective_flags['state'] = 'blocked_or_unconfirmed'
                objective_flags['verified_released'] = False
            autofocus = (None if owner.state == 'UNCERTAIN' else
                         owner.state in ('ACTIVE', 'RELEASING') and owner.current.operation in
                         ('autofocus', 'snake_autofocus'))
        objective_flags['window'] = ('NOT_CREATED' if widget is None else
            'OPEN' if hasattr(widget, 'isVisible') and widget.isVisible() else 'CLOSED')
        return dict(
            snake_workflow=(bridge.snake_parent or bridge.last_snake_parent).snapshot()
                if (bridge.snake_parent or bridge.last_snake_parent) else None,
            read_only=True, scope='Cached ownership evidence; no instrument readback or acquisition authorization',
            legacy_daq_state=ledger['state'],
            legacy_daq_cleanup_unverified=bridge.legacy_daq_cleanup_unverified,
            legacy_daq_ever_acquired=ledger['ever_acquired'],
            legacy_daq_ever_acquired_interpretation='Conservative acquisition-path evidence, not proof a native NI task was created',
            pending_acquisition_sources=pending,
            active_legacy_sources=[r for r in blockers if r.startswith(
                ('legacy_activity:', 'legacy_thread_state_unknown:', 'legacy_callback_active'))
                or r == 'legacy_daq_active'],
            objective_owner_state=objective_flags,
            autofocus_state=('unverified' if owner is None and autofocus is False else
                             'inactive' if autofocus is False else
                             'active' if autofocus is True else 'unknown'),
            session_identity=ledger['session_id'],
            context_generation=controller.registration.context_generation,
            ownership_lease_state=controller.ownership.status.value,
            current_run_id=handle.run_id if handle is not None else None,
            lease_authorities=list(handle.lease.authorities) if handle is not None else [],
            acquisition_state=controller.machine.state.value,
            ownership_reasons=list(controller.ownership.reasons),
            blockers=blockers,
            production_pre_handoff_blockers=pre_handoff,
            handoff_managed_conditions=[r for r in blockers if r in handoff_managed],
            production_ownership_blocked=bool(reasons),
            production_ownership_block_reasons=reasons,
            production_pre_handoff_error='; '.join(pre_handoff) if pre_handoff else None,
            last_attempt_error=last_message if last_message and last_message.startswith('Not started:') else None,
            unevaluated_gates='Envelope, operator confirmations, laser state and subsequent handoff/DAQ checks; no launch attempted',
            active_acquisition_ids=[r['token'] for r in ledger['transitions'] if not r['released']],
            last_completed_source=completed[-1]['source'] if completed else None,
            last_release_attestation=completed[-1] if completed else None,
            daq_transitions=ledger['transitions'])
