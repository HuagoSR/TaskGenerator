"""Versioned, structural provenance checks; no automatic professional judgments."""
from pathlib import Path

from task_generator.production.agent_factory import read, safe_path, digest


KINDS = ('explicit', 'material_instruction', 'necessary_derivation', 'optional')


def reference(ref, inputs, location):
    if not isinstance(ref, dict) or not all(isinstance(ref.get(k), str) and ref[k].strip()
                                          for k in ('path', 'locator', 'explanation', 'sha256')):
        raise ValueError(f'{location}: expected path, locator, explanation and sha256 strings')
    path = ref['path']
    if path not in ('candidate_task.md', 'deliverable_contract.json', 'public_context.json') and not path.startswith('reference_files/'):
        raise ValueError(f'{location}.path: candidate-visible sources only')
    source = safe_path(inputs, path)
    if not source.is_file() or digest(source) != ref['sha256']:
        raise ValueError(f'{location}.sha256: source missing or hash mismatch')


def indexed(value, field, key):
    rows = value.get(field)
    if not isinstance(rows, list):
        raise ValueError(f'{field}: expected a list')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f'{field}.{key}: expected nonempty ID')
        if row[key] in result:
            raise ValueError(f'{field}.{key}: duplicate ID {row[key]}')
        result[row[key]] = row
    return result


def actual_changes(initial, final):
    """IDs bind changes to real files, including credit boundaries and anchors."""
    changes = []
    for filename, field, key in (
        ('basis_draft.json', 'requirements', 'requirement_id'),
        ('new_rubric.json', 'criteria', 'criterion_id'),
        ('calculation_evidence.json', 'calculations', 'calculation_id'),
    ):
        before = indexed(read(Path(initial) / filename), field, key)
        after = indexed(read(Path(final) / filename), field, key)
        for identity in sorted(before.keys() | after.keys()):
            if before.get(identity) != after.get(identity):
                changes.append({'change_id': f'{filename}:{identity}',
                                'change_type': 'add' if identity not in before else 'remove' if identity not in after else 'clarify',
                                'before': before.get(identity), 'after': after.get(identity)})
    return changes


def validate(draft, inputs, require_comparison, initial_snapshot):
    basis = read(Path(draft) / 'basis_draft.json')
    requirements = indexed(basis, 'requirements', 'requirement_id')
    criteria = indexed(read(Path(draft) / 'new_rubric.json'), 'criteria', 'criterion_id')
    if not requirements:
        raise ValueError('basis_draft.json.requirements: expected nonempty mappings')
    mapped = set()
    for identity, row in requirements.items():
        location = f'basis_draft.json.requirements[{identity}]'
        kind = row.get('basis_kind')
        if kind not in KINDS or not isinstance(row.get('obligation'), str) or not row['obligation'].strip():
            raise ValueError(f'{location}: expected obligation and basis_kind in {KINDS}')
        refs = row.get('candidate_obligation_refs')
        if not isinstance(refs, list) or not refs:
            raise ValueError(f'{location}.candidate_obligation_refs: expected nonempty source list')
        for i, ref in enumerate(refs):
            reference(ref, inputs, f'{location}.candidate_obligation_refs[{i}]')
        ids = row.get('rubric_ids')
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids) or set(ids) - criteria.keys():
            raise ValueError(f'{location}.rubric_ids: expected unique existing criterion IDs')
        if kind == 'optional':
            if ids:
                raise ValueError(f'{location}.rubric_ids: optional analysis cannot impose scored obligations')
        elif not ids:
            raise ValueError(f'{location}.rubric_ids: scored obligation needs criterion mapping')
        if kind == 'explicit' and not any(r['path'] in ('candidate_task.md', 'deliverable_contract.json') for r in refs):
            raise ValueError(f'{location}: explicit obligation needs task or contract source')
        if kind == 'material_instruction' and not any(r['path'].startswith('reference_files/') for r in refs):
            raise ValueError(f'{location}: material instruction needs a candidate record')
        if kind == 'necessary_derivation':
            parent = row.get('serves_requirement_id')
            if parent not in requirements or requirements[parent].get('basis_kind') not in ('explicit', 'material_instruction'):
                raise ValueError(f'{location}.serves_requirement_id: expected explicit or material obligation ID')
            for key in ('necessity', 'alternative_paths'):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f'{location}.{key}: expected nonempty explanation')
        mapped.update(ids)
    missing = {k for k, v in criteria.items() if v.get('decision_id') != 'deliverable_structure'} - mapped
    if missing:
        raise ValueError(f'basis_draft.json.requirements: unmapped criteria {sorted(missing)}')
    if require_comparison:
        comparison = read(Path(draft) / 'comparison.json')
        if comparison.get('initial_basis_snapshot') != initial_snapshot or not initial_snapshot:
            raise ValueError('comparison.json.initial_basis_snapshot: immutable identity mismatch')
        changes = actual_changes(Path(inputs) / 'initial_basis', draft)
        declared = indexed(comparison, 'requirement_changes', 'change_id')
        actual = {row['change_id']: row for row in changes}
        if declared.keys() != actual.keys():
            raise ValueError(f'comparison.json.requirement_changes: expected actual change IDs {sorted(actual)}')
        old_criteria = indexed(read(Path(inputs) / 'initial_basis/new_rubric.json'), 'criteria', 'criterion_id')
        for identity, row in declared.items():
            if row.get('change_type') != actual[identity]['change_type'] or not isinstance(row.get('description'), str) or not row['description'].strip():
                raise ValueError(f'comparison.json.requirement_changes[{identity}]: expected actual change_type and explanation')
            ids = row.get('rubric_ids', [])
            if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or set(ids) - (criteria.keys() | old_criteria.keys()):
                raise ValueError(f'comparison.json.requirement_changes[{identity}].rubric_ids: unknown criterion')
            for i, ref in enumerate(row.get('candidate_obligation_refs', [])):
                reference(ref, inputs, f'comparison.json.requirement_changes[{identity}].candidate_obligation_refs[{i}]')
    return basis
