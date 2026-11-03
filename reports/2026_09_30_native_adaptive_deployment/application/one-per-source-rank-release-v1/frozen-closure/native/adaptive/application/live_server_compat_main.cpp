#include "live.hpp"
#include "../runtime/server_compat/server_compat.hpp"

#include <exception>
#include <iostream>

int main(int argc,char** argv) {
    try {
        leo::adaptive::server_compat::SupportDeriver deriver(
            leo::adaptive::server_compat::authority_binding());
        const auto port=leo::adaptive::server_compat::derivation_port(deriver);
        return leo::adaptive::application::live::run_cli_with_providers_and_support(
            argc,argv,leo_local_iio_provider(),leo_local_iio_radio_prepare_provider(),port);
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n';
        return 9;
    }
}
