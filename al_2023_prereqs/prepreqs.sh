#!/bin/bash
set -e

# 1. Install system dependencies
sudo yum install -y readline-devel

# 2. Install meson and ninja
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

# 5. Install plenv (Perl version manager)
if [ ! -d "$HOME/.plenv" ]; then
    git clone https://github.com/tokuhirom/plenv.git ~/.plenv
    git clone https://github.com/tokuhirom/Perl-Build.git ~/.plenv/plugins/perl-build/
fi

if ! grep -q 'plenv/bin' ~/.zshrc; then
    echo '' >> ~/.zshrc
    echo '# plenv (Perl version manager)' >> ~/.zshrc
    echo 'export PATH="$HOME/.plenv/bin:$PATH"' >> ~/.zshrc
    echo 'eval "$(plenv init -)"' >> ~/.zshrc
fi

# 6. Source updated zshrc
export PATH="$HOME/.plenv/bin:$HOME/.local/bin:$PATH"
eval "$(plenv init -)"
export PERL5LIB="$HOME/perl5/lib/perl5${PERL5LIB:+:${PERL5LIB}}"

# 7. Helper function: source a plenv Perl for PG plperl builds
#    Usage: source_plenv_perl <version>
#    Example: source_plenv_perl 5.38.2
source_plenv_perl() {
    local ver="$1"
    if [ -z "$ver" ]; then
        echo "Usage: source_plenv_perl <perl-version>" >&2
        return 1
    fi
    local prefix="$HOME/.plenv/versions/$ver"
    if [ ! -d "$prefix" ]; then
        echo "Perl $ver not installed. Install with: plenv install $ver -Duseshrplib" >&2
        return 1
    fi
    plenv shell "$ver"
    export LD_LIBRARY_PATH="$prefix/lib/CORE${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    echo "Active Perl: $(plenv which perl) ($(perl -v | grep version))"
}

