# Embed trace on execution
def on_vault_apply(vault_output):
    # Add glyphs to output
    vault_output['trace'] = generate_glyphs(vault_output)
    return vault_output

def generate_glyphs(output):
    # Placeholder: Generate glyphs based on output
    glyphs = []
    if output.get('action') == 'escalate':
        glyphs.append('⚠️')
    return glyphs

def generate_glyphs(output):
    # Placeholder
    return ['⚠️']