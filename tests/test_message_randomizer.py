"""Tests for message template randomizer."""

import pytest
import re
from src.service.message_randomizer import (
    randomize_template,
    extract_options_from_template,
    validate_template,
)


class TestRandomizeTemplate:
    """Test randomize_template function."""

    def test_simple_template(self):
        """Test simple template with one block."""
        template = "{Hello|Hi}"
        result = randomize_template(template)
        assert result in ["Hello", "Hi"]

    def test_multiple_blocks(self):
        """Test template with multiple blocks."""
        template = "{Hello|Hi} {world|there}!"
        result = randomize_template(template)
        
        # Check that result matches expected pattern
        assert result in [
            "Hello world!",
            "Hello there!",
            "Hi world!",
            "Hi there!",
        ]

    def test_complex_template(self):
        """Test complex template like in the issue description."""
        template = (
            "{Thanks|Thank you|Many thanks} "
            "{for checking out|for viewing|for looking at} "
            "{my work|my art|my latest work}. "
            "{I appreciate it|It means a lot|Your support means a lot}."
        )
        result = randomize_template(template)
        
        # Check that result contains expected parts
        assert any(word in result for word in ["Thanks", "Thank you", "Many thanks"])
        assert any(phrase in result for phrase in ["for checking out", "for viewing", "for looking at"])
        assert any(phrase in result for phrase in ["my work", "my art", "my latest work"])
        assert any(phrase in result for phrase in ["I appreciate it", "It means a lot", "Your support means a lot"])
        
        # Check that result doesn't contain template syntax
        assert "{" not in result
        assert "}" not in result
        assert "|" not in result

    def test_template_with_static_text(self):
        """Test template with both static and dynamic parts."""
        template = "Hello {friend|buddy}, how are you?"
        result = randomize_template(template)
        
        assert result in ["Hello friend, how are you?", "Hello buddy, how are you?"]

    def test_empty_template(self):
        """Test empty template."""
        result = randomize_template("")
        assert result == ""

    def test_template_without_blocks(self):
        """Test template without any randomization blocks."""
        template = "Hello world!"
        result = randomize_template(template)
        assert result == "Hello world!"

    def test_single_option_block(self):
        """Test block with single option (edge case)."""
        template = "{Hello} world!"
        result = randomize_template(template)
        assert result == "Hello world!"

    def test_whitespace_handling(self):
        """Test that whitespace in options is trimmed."""
        template = "{Hello | Hi | Hey} world!"
        result = randomize_template(template)
        
        # Should trim whitespace from options
        assert result in ["Hello world!", "Hi world!", "Hey world!"]
        assert "  " not in result  # No double spaces

    def test_randomness(self):
        """Test that function produces different results (probabilistic test)."""
        template = "{A|B|C|D|E|F|G|H|I|J}"
        results = set()
        
        # Run 50 times, should get multiple different results
        for _ in range(50):
            results.add(randomize_template(template))
        
        # With 10 options and 50 runs, we should get at least 5 different results
        assert len(results) >= 5

    def test_nested_braces_not_supported(self):
        """Test that nested braces are not supported (treated as literal)."""
        template = "{Hello {inner|text}|Hi}"
        result = randomize_template(template)
        
        # Should handle this gracefully (may not work perfectly, but shouldn't crash)
        assert isinstance(result, str)


class TestExtractOptionsFromTemplate:
    """Test extract_options_from_template function."""

    def test_simple_extraction(self):
        """Test extracting options from simple template."""
        template = "{Hello|Hi}"
        result = extract_options_from_template(template)
        assert result == [["Hello", "Hi"]]

    def test_multiple_blocks_extraction(self):
        """Test extracting options from multiple blocks."""
        template = "{Hello|Hi} {world|there}!"
        result = extract_options_from_template(template)
        assert result == [["Hello", "Hi"], ["world", "there"]]

    def test_complex_extraction(self):
        """Test extracting options from complex template."""
        template = "{A|B|C} {D|E} {F|G|H|I}"
        result = extract_options_from_template(template)
        assert result == [["A", "B", "C"], ["D", "E"], ["F", "G", "H", "I"]]

    def test_empty_template_extraction(self):
        """Test extracting from empty template."""
        result = extract_options_from_template("")
        assert result == []

    def test_no_blocks_extraction(self):
        """Test extracting from template without blocks."""
        template = "Hello world!"
        result = extract_options_from_template(template)
        assert result == []

    def test_whitespace_trimming(self):
        """Test that whitespace is trimmed from extracted options."""
        template = "{Hello | Hi | Hey}"
        result = extract_options_from_template(template)
        assert result == [["Hello", "Hi", "Hey"]]


class TestValidateTemplate:
    """Test validate_template function."""

    def test_valid_simple_template(self):
        """Test validation of simple valid template."""
        template = "{Hello|Hi}"
        is_valid, error = validate_template(template)
        assert is_valid is True
        assert error == ""

    def test_valid_complex_template(self):
        """Test validation of complex valid template."""
        template = (
            "{Thanks|Thank you|Many thanks} "
            "{for checking out|for viewing|for looking at} "
            "{my work|my art|my latest work}."
        )
        is_valid, error = validate_template(template)
        assert is_valid is True
        assert error == ""

    def test_empty_template_valid(self):
        """Test that empty template is considered valid."""
        is_valid, error = validate_template("")
        assert is_valid is True
        assert error == ""

    def test_no_blocks_valid(self):
        """Test that template without blocks is valid."""
        template = "Hello world!"
        is_valid, error = validate_template(template)
        assert is_valid is True
        assert error == ""

    def test_unmatched_opening_brace(self):
        """Test validation fails for unmatched opening brace."""
        template = "{Hello|Hi world!"
        is_valid, error = validate_template(template)
        assert is_valid is False
        assert "Unmatched braces" in error

    def test_unmatched_closing_brace(self):
        """Test validation fails for unmatched closing brace."""
        template = "Hello|Hi} world!"
        is_valid, error = validate_template(template)
        assert is_valid is False
        assert "Unmatched braces" in error

    def test_single_option_invalid(self):
        """Test validation fails for block with single option."""
        template = "{Hello} world!"
        is_valid, error = validate_template(template)
        assert is_valid is False
        assert "only 1 option" in error

    def test_empty_option_invalid(self):
        """Test validation fails for block with empty option."""
        template = "{Hello||Hi}"
        is_valid, error = validate_template(template)
        assert is_valid is False
        assert "empty option" in error

    def test_multiple_blocks_one_invalid(self):
        """Test validation fails if any block is invalid."""
        template = "{Hello|Hi} {world}"
        is_valid, error = validate_template(template)
        assert is_valid is False
        assert "only 1 option" in error


class TestIntegration:
    """Integration tests for the randomizer."""

    def test_validate_then_randomize(self):
        """Test typical workflow: validate then randomize."""
        template = "{Hello|Hi} {world|there}!"
        
        # First validate
        is_valid, error = validate_template(template)
        assert is_valid is True
        
        # Then randomize
        result = randomize_template(template)
        assert result in ["Hello world!", "Hello there!", "Hi world!", "Hi there!"]

    def test_real_world_example(self):
        """Test with real-world example from issue description."""
        template = (
            "{Thanks|Thank you|Many thanks} "
            "{for checking out|for viewing|for looking at} "
            "{my work|my art|my latest work}. "
            "{I appreciate it|It means a lot|Your support means a lot}."
        )
        
        # Validate
        is_valid, error = validate_template(template)
        assert is_valid is True
        
        # Randomize multiple times
        results = set()
        for _ in range(20):
            result = randomize_template(template)
            results.add(result)
            
            # Each result should be a complete sentence
            assert result.endswith(".")
            assert "{" not in result
            assert "}" not in result
            assert "|" not in result
        
        # Should produce multiple different results
        assert len(results) > 1
