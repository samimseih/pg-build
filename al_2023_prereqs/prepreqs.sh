#!/bin/bash
set -e

# 1. Install meson and ninja
pip3 install meson ninja

# 2. Add ~/.local/bin to PATH (for meson/ninja)
if ! grep -q 'HOME/.local/bin' ~/.zshrc; then
    echo '' >> ~/.zshrc
    echo '# Make sure ~/.local/bin is in your PATH if the commands aren'\''t found directly.' >> ~/.zshrc
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
fi

# 3. Install Perl IPC::Run module (required for PostgreSQL TAP tests)
cpan IPC::Run

# 4. Add PERL5LIB to ~/.zshrc so Perl can find local modules
if ! grep -q 'PERL5LIB' ~/.zshrc; then
    echo '' >> ~/.zshrc
    echo '# Perl local modules (for IPC::Run etc.)' >> ~/.zshrc
    echo 'export PERL5LIB="$HOME/perl5/lib/perl5${PERL5LIB:+:${PERL5LIB}}"' >> ~/.zshrc
fi

# 5. Source updated zshrc
export PATH="$HOME/.local/bin:$PATH"
export PERL5LIB="$HOME/perl5/lib/perl5${PERL5LIB:+:${PERL5LIB}}"

