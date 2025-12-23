"""Universal message template randomizer.

This module provides functionality to randomize message templates
with syntax {option1|option2|option3} where one option is randomly selected.

Can be used for profile broadcasting, deviation comments, and other messaging features.
"""

import re
import random
from typing import List


def randomize_template(template: str) -> str:
    """Randomize a message template by selecting random options from {opt1|opt2|opt3} blocks.
    
    Args:
        template: Message template with {option1|option2|option3} syntax
        
    Returns:
        Randomized message with one option selected from each block
        
    Example:
        >>> template = "{Hello|Hi} {world|there}!"
        >>> result = randomize_template(template)
        >>> # Result could be: "Hello world!" or "Hi there!" or "Hello there!" or "Hi world!"
    """
    if not template:
        return template
    
    # Pattern to match {option1|option2|option3}
    pattern = r'\{([^}]+)\}'
    
    def replace_block(match: re.Match) -> str:
        """Replace a single {opt1|opt2|opt3} block with random choice."""
        options_str = match.group(1)
        options = [opt.strip() for opt in options_str.split('|')]
        
        if not options:
            return match.group(0)  # Return original if no options
        
        return random.choice(options)
    
    # Replace all {opt1|opt2|opt3} blocks with random choices
    result = re.sub(pattern, replace_block, template)
    
    return result


def extract_options_from_template(template: str) -> List[List[str]]:
    """Extract all option blocks from a template for analysis/validation.
    
    Args:
        template: Message template with {option1|option2|option3} syntax
        
    Returns:
        List of option lists, one per block
        
    Example:
        >>> template = "{Hello|Hi} {world|there}!"
        >>> extract_options_from_template(template)
        [['Hello', 'Hi'], ['world', 'there']]
    """
    if not template:
        return []
    
    pattern = r'\{([^}]+)\}'
    matches = re.findall(pattern, template)
    
    result = []
    for match in matches:
        options = [opt.strip() for opt in match.split('|')]
        result.append(options)
    
    return result


def validate_template(template: str) -> tuple[bool, str]:
    """Validate a message template syntax.
    
    Args:
        template: Message template to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> validate_template("{Hello|Hi} world!")
        (True, "")
        >>> validate_template("{Hello} world!")
        (False, "Block at position 0 has only 1 option, need at least 2")
    """
    if not template:
        return True, ""
    
    # Check for unmatched braces
    open_count = template.count('{')
    close_count = template.count('}')
    
    if open_count != close_count:
        return False, f"Unmatched braces: {open_count} opening, {close_count} closing"
    
    # Extract and validate option blocks
    options_list = extract_options_from_template(template)
    
    for i, options in enumerate(options_list):
        if len(options) < 2:
            return False, f"Block at position {i} has only {len(options)} option, need at least 2"
        
        # Check for empty options
        if any(not opt for opt in options):
            return False, f"Block at position {i} contains empty option"
    
    return True, ""
