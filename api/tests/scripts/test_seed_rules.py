"""
Tests for the seed_rules script.
"""

from db.models import ValidationRule


class TestSeedRules:
    def test_seed_adds_rules(self, db_session):
        """Seeding an empty database adds all default rules."""
        from scripts.seed_rules import seed

        # Confirm no rules exist yet
        count_before = db_session.query(ValidationRule).count()

        seed()

        count_after = db_session.query(ValidationRule).count()
        assert count_after > count_before

    def test_seed_is_idempotent(self, db_session):
        """Running seed twice does not create duplicate rules."""
        from scripts.seed_rules import seed

        seed()
        count_after_first = db_session.query(ValidationRule).count()

        seed()
        count_after_second = db_session.query(ValidationRule).count()

        assert count_after_first == count_after_second

    def test_seed_creates_required_rules(self, db_session):
        """Seed must create required-type rules."""
        from scripts.seed_rules import seed

        seed()

        required_rules = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.rule_type == "required")
            .all()
        )
        assert len(required_rules) > 0

    def test_seed_creates_format_rules(self, db_session):
        """Seed must create format rules including NIN and BVN."""
        from scripts.seed_rules import seed

        seed()

        nin_rule = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.field == "NIN")
            .first()
        )
        bvn_rule = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.field == "BVN")
            .first()
        )

        assert nin_rule is not None
        assert bvn_rule is not None
        assert nin_rule.rule_type == "format"
        assert bvn_rule.rule_type == "format"

    def test_seed_creates_logical_rules(self, db_session):
        """Seed must create logical rules for age and expiry checks."""
        from scripts.seed_rules import seed

        seed()

        logical_rules = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.rule_type == "logical")
            .all()
        )
        checks = [r.check for r in logical_rules]

        assert "min_age_18" in checks
        assert "not_expired" in checks
        assert "not_future" in checks

    def test_seed_creates_cross_doc_rule(self, db_session):
        """Seed must create at least one cross_doc rule."""
        from scripts.seed_rules import seed

        seed()

        cross_doc_rules = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.rule_type == "cross_doc")
            .all()
        )
        assert len(cross_doc_rules) > 0

    def test_seed_rules_are_enabled_by_default(self, db_session):
        """All seeded rules must be enabled by default."""
        from scripts.seed_rules import seed

        seed()

        disabled = (
            db_session.query(ValidationRule)
            .filter(
                ValidationRule.id.like("rule_default_%"),
                ValidationRule.is_enabled.is_(False),
            )
            .all()
        )
        assert len(disabled) == 0

    def test_seed_nin_pattern_is_correct(self, db_session):
        """NIN rule must have the 11-digit pattern."""
        from scripts.seed_rules import seed

        seed()

        nin_rule = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.field == "NIN")
            .first()
        )
        assert nin_rule.pattern == r"^\d{11}$"

    def test_seed_account_number_pattern_is_correct(self, db_session):
        """Account number rule must have the 10-digit NUBAN pattern."""
        from scripts.seed_rules import seed

        seed()

        rule = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.field == "Account Number")
            .first()
        )
        assert rule.pattern == r"^\d{10}$"

    def test_seed_reset_removes_and_recreates_rules(self, db_session):
        """Reset flag removes existing default rules and re-seeds."""
        from scripts.seed_rules import seed

        seed()
        count_after_first = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.id.like("rule_default_%"))
            .count()
        )

        seed(reset=True)
        count_after_reset = (
            db_session.query(ValidationRule)
            .filter(ValidationRule.id.like("rule_default_%"))
            .count()
        )

        assert count_after_reset == count_after_first
