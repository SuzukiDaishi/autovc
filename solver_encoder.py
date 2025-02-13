from model_vc import Generator
import torch
import torch.nn.functional as F
import time
import datetime
from torch.utils.tensorboard import SummaryWriter

class Solver(object):

    def __init__(self, vcc_loader, config):
        """Initialize configurations."""

        # Data loader.
        self.vcc_loader = vcc_loader

        # Model configurations.
        self.lambda_cd = config.lambda_cd
        self.dim_neck = config.dim_neck
        self.dim_emb = config.dim_emb
        self.dim_pre = config.dim_pre
        self.freq = config.freq

        # Training configurations.
        self.batch_size = config.batch_size
        self.num_iters = config.num_iters
        
        # Miscellaneous.
        self.use_cuda = torch.cuda.is_available()
        self.device = torch.device('cuda:0' if self.use_cuda else 'cpu')
        self.log_step = config.log_step

        # Adam
        self.g_lr = config.g_lr
        self.beta1 = config.beta1
        self.beta2 = config.beta2

        # Build the model and tensorboard.
        self.save_path = config.save_path
        self.save_step = config.save_step
        self.writer = SummaryWriter(log_dir='./runs')
        self.build_model(config.checkpoint)

            
    def build_model(self, checkpoint = None):
        
        self.G = Generator(self.dim_neck, self.dim_emb, self.dim_pre, self.freq)        
        
        self.g_optimizer = torch.optim.Adam(self.G.parameters(), self.g_lr, [self.beta1, self.beta2])
        
        self.G.to(self.device)

        if checkpoint is not None:
            g_checkpoint = None
            if torch.cuda.is_available():
                g_checkpoint = torch.load(checkpoint)
            else :
                g_checkpoint = torch.load(checkpoint, map_location='cpu')
            self.G.load_state_dict(g_checkpoint)

    def reset_grad(self):
        """Reset the gradient buffers."""
        self.g_optimizer.zero_grad()
      
    def save_losses(self, loss_id, loss_id_psnt, loss_cd, iter_num):
        """ save tensorbord """
        self.writer.add_scalar('loss_id/train', loss_id, iter_num)
        self.writer.add_scalar('loss_id_psnt/train', loss_id_psnt, iter_num)
        self.writer.add_scalar('loss_cd/train', loss_cd, iter_num)

    #=====================================================================================================================================#
    
    
                
    def train(self):
        # Set data loader.
        data_loader = self.vcc_loader
        
        # Print logs in specified order
        keys = ['G/loss_id','G/loss_id_psnt','G/loss_cd']
            
        # Start training.
        print('Start training...')
        start_time = time.time()
        for i in range(self.num_iters):

            # =================================================================================== #
            #                             1. Preprocess input data                                #
            # =================================================================================== #

            # Fetch data.
            try:
                x_real, emb_org = next(data_iter)
            except:
                data_iter = iter(data_loader)
                x_real, emb_org = next(data_iter)
            
            
            x_real = x_real.to(self.device) 
            emb_org = emb_org.to(self.device) 

            # =================================================================================== #
            #                               2. Train the generator                                #
            # =================================================================================== #
            
            self.G = self.G.train()
                        
            # Identity mapping loss
            x_identic, x_identic_psnt, code_real = self.G(x_real, emb_org, emb_org)
            g_loss_id = F.mse_loss(x_real, x_identic)   
            g_loss_id_psnt = F.mse_loss(x_real, x_identic_psnt)   
            
            # Code semantic loss.
            code_reconst = self.G(x_identic_psnt, emb_org, None)
            g_loss_cd = F.l1_loss(code_real, code_reconst)


            # Backward and optimize.
            g_loss = g_loss_id + g_loss_id_psnt + self.lambda_cd * g_loss_cd
            self.reset_grad()
            g_loss.backward()
            self.g_optimizer.step()

            # Logging.
            loss = {}
            loss['G/loss_id'] = g_loss_id.item()
            loss['G/loss_id_psnt'] = g_loss_id_psnt.item()
            loss['G/loss_cd'] = g_loss_cd.item()

            self.save_losses(loss['G/loss_id'], loss['G/loss_id_psnt'], loss['G/loss_cd'], i+1)

            # =================================================================================== #
            #                                 4. Miscellaneous                                    #
            # =================================================================================== #

            # Print out training information.
            if (i+1) % self.log_step == 0:
                et = time.time() - start_time
                et = str(datetime.timedelta(seconds=et))[:-7]
                log = "Elapsed [{}], Iteration [{}/{}]".format(et, i+1, self.num_iters)
                for tag in keys:
                    log += ", {}: {:.4f}".format(tag, loss[tag])
                print(log)
                
            if (i+1) % self.save_step == 0:
                torch.save(self.G.state_dict(), self.save_path)
                print(f'saved {self.save_path}')
        
        torch.save(self.G.state_dict(), self.save_path)
        print(f'saved {self.save_path}')